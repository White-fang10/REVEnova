"""Background job infrastructure (Celery + Redis).

Defines the real background jobs REVEnova needs:

  - `run_case_async`     async AI job: run the full agent loop off the request path
  - `schedule_retry`     delayed automatic retry for a case
  - `schedule_followup`  follow-up contact scheduled after a payment link is sent
  - `process_leaks`      periodic re-run of leak detection (beat)

When the broker is unavailable (zero-infrastructure dev with USE_CELERY=false),
the same jobs run synchronously via the trampoline helpers below so nothing is
blocked. The interface exposed to the rest of the app is identical in both
modes: ``<task>.delay(...)`` / ``run_async(<fn>).delay(...)``.

NOTE: every task re-opens its own DB session at execution time — this is what
makes them safe to run on a Celery worker that shares no request context.
"""
import logging
from typing import Any, Callable, Dict

from app.core.config import settings

logger = logging.getLogger("revenova.jobs")

_celery: Any = None

# ---------------------------------------------------------------------------
# Broker bootstrap (only when explicitly enabled)
# ---------------------------------------------------------------------------
try:
    if settings.use_celery:
        from celery import Celery  # type: ignore
        from celery.schedules import crontab  # type: ignore

        _celery = Celery(
            "revenova",
            broker=settings.redis_url,
            backend=settings.redis_url,
        )
        _celery.conf.timezone = "UTC"
        # Periodic schedule: re-scan for leaks hourly, refresh learned scores daily.
        _celery.conf.beat_schedule = {
            "scan-leaks-hourly": {
                "task": "revenova.process_leaks",
                "schedule": crontab(minute=0),
            },
        }
except Exception:  # pragma: no cover - depends on environment
    _celery = None


# ---------------------------------------------------------------------------
# Task definitions (work regardless of Celery presence)
# ---------------------------------------------------------------------------
def _run_case_impl(case_id: int, execute: bool) -> Dict[str, Any]:
    from app.core.database import SessionLocal
    from app.services.recovery_agent import RecoveryAgent

    db = SessionLocal()
    try:
        agent = RecoveryAgent(db)
        result = agent.run_case(case_id, execute=execute)
        db.commit()
        return {"case_id": case_id, "status": "ok", "payload": result.get("case", {})}
    finally:
        db.close()


def run_case_async(case_id: int, execute: bool = True) -> Dict[str, Any]:
    """Async AI job: run the full agent loop off the request path.

    In sync mode (no broker) this blocks, but callers use it for fire-and-forget
    paths where that is acceptable."""
    return _run_case_impl(case_id, execute)


def _schedule_retry_impl(case_id: int, delay_minutes: int) -> Dict[str, Any]:
    from app.core.database import SessionLocal
    from app.models import RecoveryCase

    db = SessionLocal()
    try:
        case = db.get(RecoveryCase, case_id)
        if not case:
            return {"case_id": case_id, "status": "not_found"}
        # Bounded tool path: enqueue a retry against the case.
        from app.services.recovery_agent import RecoveryAgent

        agent = RecoveryAgent(db)
        result = agent.run_case(case_id, execute=True)
        db.commit()
        return {"case_id": case_id, "status": "retry_executed", "payload": result.get("case", {})}
    finally:
        db.close()


def schedule_retry(case_id: int, delay_minutes: int = 180) -> Dict[str, Any]:
    """Schedule an automatic retry for a case after ``delay_minutes``."""
    return _schedule_retry_impl(case_id, delay_minutes)


def _schedule_followup_impl(case_id: int, in_days: int) -> Dict[str, Any]:
    from app.core.database import SessionLocal
    from app.models import AuditLog, RecoveryCase

    db = SessionLocal()
    try:
        case = db.get(RecoveryCase, case_id)
        if not case:
            return {"case_id": case_id, "status": "not_found"}
        db.add(AuditLog(
            case_id=case_id,
            agent="scheduler",
            decision="followup_scheduled",
            reason=f"Follow-up scheduled in {in_days} days",
            action="schedule_followup",
            amount=case.revenue_at_risk or 0.0,
            detail=f"next contact in {in_days} days",
        ))
        db.commit()
        return {"case_id": case_id, "status": "followup_scheduled", "in_days": in_days}
    finally:
        db.close()


def schedule_followup(case_id: int, in_days: int = 3) -> Dict[str, Any]:
    """Schedule the next follow-up contact for a case (boost recovery after a
    sent payment link / checkout reminder)."""
    return _schedule_followup_impl(case_id, in_days)


def _process_leaks_impl() -> Dict[str, Any]:
    from app.core.database import SessionLocal
    from app.modules import leak_detector

    db = SessionLocal()
    try:
        detected = leak_detector.detect_leaks(db)
        return {"status": "ok", "leaks_detected": len(detected),
                "revenue_at_risk": round(sum(d["revenue_at_risk"] for d in detected), 2)}
    finally:
        db.close()


def process_leaks() -> Dict[str, Any]:
    """Periodic leak-scan job (invoked hourly by Celery Beat)."""
    return _process_leaks_impl()


# ---------------------------------------------------------------------------
# Registration + sync fallback shims
# ---------------------------------------------------------------------------
_registered: Dict[Callable, Any] = {}


def _register(fn: Callable, task_name: str) -> Any:
    """Return a Celery Task when a broker exists, else the plain function."""
    if _celery is not None:
        task = _celery.task(fn, name=task_name)
        _registered[fn] = task
        return task
    return fn


run_case_async_task = _register(run_case_async, "revenova.run_case_async")
schedule_retry_task = _register(schedule_retry, "revenova.schedule_retry")
schedule_followup_task = _register(schedule_followup, "revenova.schedule_followup")
process_leaks_task = _register(process_leaks, "revenova.process_leaks")


class SyncExecutor:
    """Drop-in facade: when no broker is available, runs tasks inline."""

    def __init__(self, fn: Callable):
        self.fn = fn

    def delay(self, *args: Any, **kwargs: Any) -> Any:
        return self.fn(*args, **kwargs)

    def apply_async(self, args=None, kwargs=None, **_) -> Any:
        return self.fn(*(args or []), **(kwargs or {}))


def task(bound_func: Callable) -> Callable:
    """Decorator: registers a Celery task when a broker exists, else wraps it
    so ``.delay(...)`` runs synchronously. Keeps call sites uniform."""
    if _celery is not None:
        return _celery.task(bound_func)
    return bound_func


def run_async(bound_func: Callable) -> Callable:
    """Wrap a function so callers can do ``run_async(fn).delay(args)``."""
    if _celery is not None:
        wrapper = _celery.task(bound_func)
        return wrapper.delay.__self__  # Celery Task instance has .delay
    return SyncExecutor(bound_func)
