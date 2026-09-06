"""Background job infrastructure.

Uses Celery + Redis when configured. When the broker is unavailable (as in a
zero-infrastructure dev environment), the same jobs run synchronously via the
trampoline helpers below so nothing blocks. The interface exposed to the rest
of the app is identical in both modes.
"""
import logging
from typing import Any, Callable, Dict

from app.core.config import settings

logger = logging.getLogger("revenova.jobs")

try:
    if settings.use_celery:
        from celery import Celery  # type: ignore

        celery_app = Celery(
            "revenova",
            broker="redis://localhost:6379/0",
            backend="redis://localhost:6379/0",
        )
    else:
        celery_app = None
except Exception:  # pragma: no cover
    celery_app = None


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
    if celery_app is not None:
        return celery_app.task(bound_func)
    return bound_func


def run_async(bound_func: Callable) -> Callable:
    """Wrap a function so callers can do ``run_async(fn).delay(args)``."""
    if celery_app is not None:
        wrapper = celery_app.task(bound_func)
        return wrapper.delay.__self__  # Celery Task instance has .delay
    return SyncExecutor(bound_func)