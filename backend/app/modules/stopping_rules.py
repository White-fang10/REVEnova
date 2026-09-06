"""Stopping Rules — deterministic circuit breakers.

The system must know when to STOP, not just when to act. Every rule here is a
pure deterministic function of facts recorded on the case, so it is fully
testable and auditable.

Rules:
  - S01: stop after N consecutive failed recovery attempts
  - S02: stop automated recovery when predicted recovery probability < minimum
  - S03: stop contacting a customer after N contacts within 7 days
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.core.config import settings


@dataclass
class StoppingDecision:
    should_stop: bool
    reason: str = ""
    rule_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"should_stop": self.should_stop, "reason": self.reason, "rule_id": self.rule_id}


def should_stop(
    consecutive_failures: int = 0,
    recovery_probability: float = 1.0,
    contacts_in_7d: int = 0,
    max_consecutive_failures: Optional[int] = None,
    min_probability: Optional[float] = None,
    max_contacts: Optional[int] = None,
) -> StoppingDecision:
    """Evaluate all stopping rules. Returns first trigger (deterministic order:
    consecutive-failure breakers take priority, then probability, then contact)."""
    max_fail = max_consecutive_failures if max_consecutive_failures is not None else settings.max_consecutive_failures
    min_prob = min_probability if min_probability is not None else settings.min_recovery_probability
    max_c = max_contacts if max_contacts is not None else settings.max_contacts_7d

    if consecutive_failures >= max_fail:
        return StoppingDecision(
            should_stop=True,
            reason=f"{consecutive_failures} consecutive failed recovery attempts (limit {max_fail})",
            rule_id="S01",
        )

    if recovery_probability < min_prob:
        return StoppingDecision(
            should_stop=True,
            reason=f"Recovery probability {recovery_probability:.1%} below the {min_prob:.0%} minimum for automated recovery",
            rule_id="S02",
        )

    if contacts_in_7d >= max_c:
        return StoppingDecision(
            should_stop=True,
            reason=f"Customer contacted {contacts_in_7d} times within 7 days (limit {max_c})",
            rule_id="S03",
        )

    return StoppingDecision(should_stop=False)


def contacts_within_7d(contact_timestamps: List[datetime], now: Optional[datetime] = None) -> int:
    """Count how many contacts fell within the trailing 7-day window."""
    if not contact_timestamps:
        return 0
    if now is None:
        now = datetime.utcnow()
    cutoff = now - timedelta(days=7)
    return sum(1 for ts in contact_timestamps if ts >= cutoff)


def is_profitable(expected_value: float, threshold: float = 0.0) -> bool:
    """Deterministic economic gate — never execute an action with negative
    expected value. (Pure function; used by the executor.)"""
    return expected_value >= threshold