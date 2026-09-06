"""Policy Engine — deterministic guardrails.

Every AI-proposed action MUST pass through this module before it can execute.
This file contains only pure, deterministic code. No LLM involvement. Ever.

The Policy Engine is deliberately written as a pure module (no DB dependency)
so it can be unit-tested exhaustively and reasoned about independently of the
rest of the system.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.core.config import settings


@dataclass
class PolicyResult:
    """Result of evaluating a proposed action against the policy engine."""

    allowed: bool
    status: str = "allowed"  # allowed | blocked | approval_required
    rule_id: Optional[str] = None
    rule: Optional[str] = None
    message: str = ""
    requires_human_approval: bool = False
    checks: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_audit(self) -> Dict[str, Any]:
        """Compact summary for the audit log."""
        return {
            "allowed": self.allowed,
            "status": self.status,
            "rule_id": self.rule_id,
            "rule": self.rule,
            "message": self.message,
        }


def check_amount_approval(
    amount: float,
    threshold: Optional[float] = None,
) -> Dict[str, Any]:
    """Rule 01 — transaction amount above the threshold needs human approval."""
    threshold = threshold if threshold is not None else settings.human_approval_threshold
    ok = amount <= threshold
    return {
        "rule_id": "R01",
        "rule": f"Transaction amount > ₹{threshold:,.0f} requires human approval",
        "passed": ok,
        "requires_human_approval": not ok,
        "message": "" if ok else f"Amount ₹{amount:,.0f} exceeds the ₹{threshold:,.0f} automatic-approval cap",
    }


def check_retry_limit(
    existing_retries: int,
    max_retries: Optional[int] = None,
) -> Dict[str, Any]:
    """Rule 02 — maximum automatic retries (default 2).

    Returns a PASS if the new retry would be at or below the cap.
    """
    max_retries = max_retries if max_retries is not None else settings.max_auto_retries
    # existing_retries counts retries already executed for this case.
    ok = existing_retries < max_retries
    return {
        "rule_id": "R02",
        "rule": f"Maximum automatic retries = {max_retries}",
        "passed": ok,
        "requires_human_approval": False,
        "message": "" if ok else f"Retry limit reached ({existing_retries} >= {max_retries}); further retries require human approval",
    }


def check_discount(
    discount_pct: float,
    max_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """Rule 03 — never offer a discount above the cap without human approval."""
    max_pct = max_pct if max_pct is not None else settings.max_discount_pct
    ok = discount_pct <= max_pct
    return {
        "rule_id": "R03",
        "rule": f"Never offer a discount > {max_pct:g}% without human approval",
        "passed": ok,
        "requires_human_approval": not ok,
        "message": "" if ok else f"Discount {discount_pct:g}% exceeds the automatic cap of {max_pct:g}%",
    }


def check_contact_frequency(
    contacts_in_7d: int,
    now: Optional[datetime] = None,
    max_contacts: Optional[int] = None,
    contact_times: Optional[List[datetime]] = None,
) -> Dict[str, Any]:
    """Rule 04 — never contact a customer more than N times in 7 days."""
    max_contacts = max_contacts if max_contacts is not None else settings.max_contacts_7d

    if contact_times is None:
        count = contacts_in_7d
    else:
        if now is None:
            now = datetime.utcnow()
        cutoff = now - timedelta(days=7)
        count = sum(1 for t in contact_times if t >= cutoff)

    ok = count < max_contacts
    return {
        "rule_id": "R04",
        "rule": f"Never contact a customer more than {max_contacts} times in 7 days",
        "passed": ok,
        "requires_human_approval": False,
        "message": "" if ok else f"Customer already contacted {count} times in the last 7 days (cap {max_contacts})",
    }


def check_high_value_escalation(
    lifetime_value: float,
    threshold: float = 200_000.0,
) -> Dict[str, Any]:
    """Rule 05 — high-value customers may always be escalated to a human."""
    ok = lifetime_value >= threshold
    return {
        "rule_id": "R05",
        "rule": "High-value customers (LTV >= ₹%s) may always be escalated to human support" % f"{threshold:,.0f}",
        "passed": ok,
        "requires_human_approval": False,
        "message": "" if ok else "LTV below high-value escalation threshold",
    }


def create_contact_counts(
    contact_count: int,
    additional: int = 1,
) -> Dict[str, Any]:
    """Helper for tests: build a contact count context."""
    return {"contacts_in_7d": contact_count + additional}


def evaluate_action(action: str, context: Dict[str, Any]) -> PolicyResult:
    """Deterministic policy gate for a proposed recovery action.

    ``action`` is a canonical action name (see CONTACT_ACTIONS / RETRY_ACTIONS /
    DISCOUNT_ACTIONS below). ``context`` supplies the facts the rules need:

        amount            - transaction amount (₹)
        existing_retries  - number of retries already executed for the case
        discount_pct      - proposed discount percentage (discount actions only)
        contacts_in_7d    - customer contacts in the last 7 days
        lifetime_value    - customer LTV (for high-value escalation)

    Returns a PolicyResult. ``allowed`` True means the action can proceed
    without human approval.
    """
    checks: List[Dict[str, Any]] = []
    verdicts = PolicyResult(allowed=True)

    amount = float(context.get("amount", 0.0))
    existing_retries = int(context.get("existing_retries", 0))
    contact_count = int(context.get("contacts_in_7d", context.get("contact_count", 0)))
    lifetime_value = float(context.get("lifetime_value", 0.0))

    # Every monetary action checks the amount rule first.
    amount_check = check_amount_approval(amount)
    checks.append(amount_check)

    if action in ("send_payment_link", "generate_payment_link", "execute_retry", "delayed_retry"):
        retry_check = check_retry_limit(existing_retries)
        checks.append(retry_check)

        # Contacts: payment-link sends and payment offers count as contact.
        contact_check = check_contact_frequency(contact_count + (1 if action != "execute_retry" else 0))
        checks.append(contact_check)
    elif action in ("call_center", "escalate_to_human", "human_escalation", "escalate"):
        # Escalation is allowed; high-value customers are always eligible.
        hv = check_high_value_escalation(lifetime_value)
        checks.append(hv)
    elif action in ("offer_discount", "apply_discount", "discount"):
        discount_pct = float(context.get("discount_pct", 0.0))
        discount_check = check_discount(discount_pct)
        checks.append(discount_check)
    elif action in ("send_notification", "send_recovery_email", "send_reminder"):
        contact_check = check_contact_frequency(contact_count + 1)
        checks.append(contact_check)
    elif action in ("stop_recovery", "close_case", "record_outcome"):
        # Bookkeeping actions are always permitted.
        ok_check = {"rule_id": "R00", "rule": "Bookkeeping action", "passed": True, "requires_human_approval": False, "message": ""}
        checks.append(ok_check)
    else:
        # Unknown action: fail closed.
        ok_check = {
            "rule_id": "R00",
            "rule": "Unknown/unsupported action — treated as not permitted",
            "passed": False,
            "requires_human_approval": True,
            "message": f"Unrecognised action '{action}'",
        }
        checks.append(ok_check)

    # Aggregate decisions deterministically.
    failed = [c for c in checks if not c["passed"]]
    needs_approval = [c for c in checks if c.get("requires_human_approval")]

    if needs_approval:
        verdicts.allowed = False
        verdicts.status = "approval_required"
        verdicts.rule_id = needs_approval[0]["rule_id"]
        verdicts.rule = needs_approval[0]["rule"]
        verdicts.message = needs_approval[0]["message"]
        verdicts.requires_human_approval = True
    elif failed:
        verdicts.allowed = False
        verdicts.status = "blocked"
        verdicts.rule_id = failed[0]["rule_id"]
        verdicts.rule = failed[0]["rule"]
        verdicts.message = failed[0]["message"]
    else:
        verdicts.allowed = True
        verdicts.status = "allowed"

    verdicts.checks = checks
    return verdicts


# Canonical action families used for routing in higher layers.
CONTACT_ACTIONS = {"send_payment_link", "send_notification", "send_recovery_email", "send_reminder", "generate_customer_message"}
RETRY_ACTIONS = {"execute_retry", "delayed_retry"}
DISCOUNT_ACTIONS = {"offer_discount", "apply_discount", "discount"}
ESCALATE_ACTIONS = {"escalate_to_human", "human_escalation", "escalate", "call_center"}