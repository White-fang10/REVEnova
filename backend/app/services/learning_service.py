"""Learning Loop — outcomes feed back into future strategy selection.

Every recorded recovery outcome updates a per-strategy running estimate. The
next time the strategy generator proposes candidates, it can read the learned
historical recovery rate for each strategy slot and blend it into the baseline.

IMPORTANT (positioning): outcomes are *captured* and improve *future strategy
selection*. The system does not claim to "learn automatically from everything"
— it improves a specific score based on observed, recorded outcomes only.
"""
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import RecoveryAction, RecoveryOutcome, RecoveryCase

logger = logging.getLogger("revenova.learning")


class LearningService:
    """In-process learning loop over the outcome tables.

    Guarantees:
      - learned scores are computed ONLY from recorded recovery_outcomes;
      - updates are only applied after outcomes are committed;
      - nothing is "auto-learned" from unmeasured events.
    """

    def __init__(self):
        self._cache: Dict[str, Dict[str, float]] = {}
        self._dirty = True

    def _invalidate(self) -> None:
        self._dirty = True

    def snapshot(self, db: Session) -> List[Dict[str, Any]]:
        """Per-strategy learned recovery stats from recorded outcomes."""
        rows = (
            db.query(
                RecoveryAction.strategy_id.label("strategy_id"),
                RecoveryOutcome.success,
                func.count().label("n"),
                func.sum(RecoveryOutcome.amount_recovered).label("total"),
            )
            .join(RecoveryOutcome, RecoveryOutcome.action_id == RecoveryAction.id)
            .group_by(RecoveryAction.strategy_id, RecoveryOutcome.success)
            .all()
        )
        totals: Dict[int, Dict[str, float]] = {}
        for strategy_id, success, n, total in rows:
            if strategy_id not in totals:
                totals[strategy_id] = {"attempts": 0.0, "successes": 0.0, "recovered": 0.0}
            totals[strategy_id]["attempts"] += float(n or 0)
            if success:
                totals[strategy_id]["successes"] += float(n or 0)
                totals[strategy_id]["recovered"] += float(total or 0)

        # recover the strategy keys by looking up strategy rows
        from app.models import RecoveryStrategy

        result: List[Dict[str, Any]] = []
        for strategy_id, t in totals.items():
            strat = db.get(RecoveryStrategy, strategy_id)
            key = strat.strategy if strat else f"strategy_{strategy_id}"
            rate = t["successes"] / t["attempts"] if t["attempts"] else 0.0
            result.append({
                "strategy": key,
                "attempts": int(t["attempts"]),
                "successes": int(t["successes"]),
                "recovery_rate": round(rate, 3),
                "amount_recovered": round(t["recovered"], 2),
            })
        # Fold multiple rows per strategy key into one.
        by_key: Dict[str, Dict[str, float]] = {}
        for r in result:
            k = r["strategy"]
            if k not in by_key:
                by_key[k] = {"attempts": 0.0, "successes": 0.0, "amount": 0.0}
            by_key[k]["attempts"] += r["attempts"]
            by_key[k]["successes"] += r["successes"]
            by_key[k]["amount"] += r["amount_recovered"]
        merged = [
            {
                "strategy": k,
                "attempts": int(v["attempts"]),
                "successes": int(v["successes"]),
                "recovery_rate": round(v["successes"] / v["attempts"], 3) if v["attempts"] else 0.0,
                "amount_recovered": round(v["amount"], 2),
            }
            for k, v in by_key.items()
        ]
        return sorted(merged, key=lambda x: x["amount_recovered"], reverse=True)

    def context(self, map_key: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Return the learned recovery-rate per strategy slot for the LLM's
        strategy-generation prompt. Populated from the last snapshot."""
        if not self._cache:
            return {}
        return dict(self._cache)

    def load(self, db: Session) -> None:
        snap = self.snapshot(db)
        self._cache = {}
        for s in snap:
            self._cache[s["strategy"]] = s["recovery_rate"]
        self._dirty = False

    def record(self, strategy_key: str, success: bool) -> None:
        """Called AFTER an outcome row is committed — updates in-memory cache
        so subsequent runs reflect the new evidence."""
        cur = self._cache.get(strategy_key, {"n": 0, "ok": 0})
        cur["n"] += 1
        cur["ok"] += 1 if success else 0
        self._cache[strategy_key] = cur["ok"] / cur["n"] if cur["n"] else 0.0
        self._dirty = True

    @property
    def summary(self) -> str:
        if not self._cache:
            return "no learned evidence yet"
        parts = " | ".join(f"{k}: {v:.0%}" for k, v in list(self._cache.items())[:5])
        return parts


learning = LearningService()