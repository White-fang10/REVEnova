"""AI Recovery Agent — bounded, auditable toolset.

The agent never touches the database directly. It reasons via the LLM and
acts only through a fixed registry of tools:

    get_customer, get_transaction, get_payment_history, get_failure_details,
    get_recovery_history, check_policy, calculate_recovery_score,
    generate_customer_message, execute_retry, send_payment_link,
    schedule_followup, escalate_to_human, record_outcome

Every tool call is logged to the audit trail with: which policy was checked,
what the result was, what action executed, and what happened afterward.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models import Customer, RecoveryAction, RecoveryCase, RecoveryStrategy, Transaction

logger = logging.getLogger("revenova.agent")


class AgentError(Exception):
    pass


class ToolTrace:
    """A single audited tool invocation during the agent workflow."""

    def __init__(self, tool: str, args: Dict[str, Any], note: str = ""):
        self.tool = tool
        self.args = args
        self.note = note
        self.created_at = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool": self.tool,
            "args": {k: v for k, v in self.args.items() if k not in ("db",)},
            "note": self.note,
            "at": self.created_at,
        }


class AgentTools:
    """The fixed read-only intelligence toolset + execution primitives.

    Executing tools return dry-run primitives; the orchestrator gates them
    through the Policy Engine before anything is recorded as having happened.
    """

    def __init__(self, db: Session):
        self.db = db
        self.trace: list[ToolTrace] = []

    # ------------------------------------------------------------------
    def _trace(self, tool: str, args: Dict[str, Any], note: str = "") -> Dict[str, Any]:
        tr = ToolTrace(tool, args, note)
        self.trace.append(tr)
        return tr.to_dict()

    def _customer_for_tx(self, tx: Transaction) -> Optional[Customer]:
        if not tx.customer_id:
            return None
        return self.db.get(Customer, tx.customer_id)

    # ------------------------------------------------------------------
    # Read-only intelligence tools
    # ------------------------------------------------------------------
    def get_customer(self, customer_id: int = 0, tx: Optional[Transaction] = None) -> Dict[str, Any]:
        cust = self.db.get(Customer, customer_id) if customer_id else (self._customer_for_tx(tx) if tx else None)
        self._trace("get_customer", {"customer_id": customer_id or (cust.id if cust else None)})
        if not cust:
            return {}
        return {
            "id": cust.id,
            "customer_ref": cust.customer_ref,
            "name": cust.name,
            "segment": cust.segment,
            "lifetime_value": cust.lifetime_value,
            "payment_method": cust.payment_method,
        }

    def get_transaction(self, transaction_id: int = 0, tx: Optional[Transaction] = None) -> Dict[str, Any]:
        t = self.db.get(Transaction, transaction_id) if transaction_id else tx
        self._trace("get_transaction", {"transaction_id": transaction_id or (t.id if t else None)})
        if not t:
            return {}
        return {
            "id": t.id,
            "transaction_ref": t.transaction_rev,
            "customer_id": t.customer_id,
            "amount": t.amount,
            "payment_method": t.payment_method,
            "device": t.device,
            "status": t.status,
            "failure_reason": t.failure_reason,
            "timestamp": t.timestamp.isoformat() if t.timestamp else None,
        }

    def get_payment_history(self, customer_id: int) -> Dict[str, Any]:
        rows = (
            self.db.query(Transaction)
            .filter(Transaction.customer_id == customer_id)
            .order_by(desc(Transaction.timestamp))
            .limit(20)
            .all()
        )
        total = len(rows)
        succeeded = sum(1 for r in rows if r.status == "succeeded")
        self._trace("get_payment_history", {"customer_id": customer_id})
        return {
            "total_transactions": total,
            "succeeded": succeeded,
            "success_rate": round(succeeded / total, 2) if total else 0.0,
            "recent": [
                {
                    "amount": r.amount,
                    "status": r.status,
                    "failure_reason": r.failure_reason,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                }
                for r in rows[:5]
            ],
        }

    def get_failure_details(self, tx_id: int = 0, tx: Optional[Transaction] = None) -> Dict[str, Any]:
        t = self.db.get(Transaction, tx_id) if tx_id else tx
        self._trace("get_failure_details", {"transaction_id": tx_id})
        if not t:
            return {}
        same_reason = (
            self.db.query(Transaction)
            .filter(
                Transaction.failure_reason == t.failure_reason,
                Transaction.timestamp >= datetime.utcnow() - timedelta(hours=24),
            )
            .count()
        )
        return {
            "failure_reason": t.failure_reason,
            "payment_method": t.payment_method,
            "device": t.device,
            "amount": t.amount,
            "same_reason_24h": same_reason,
            "window": "24h",
        }

    def get_recovery_history(self, case_id: int) -> Dict[str, Any]:
        rows = (
            self.db.query(RecoveryAction)
            .filter(RecoveryAction.case_id == case_id)
            .order_by(desc(RecoveryAction.timestamp))
            .all()
        )
        self._trace("get_recovery_history", {"case_id": case_id})
        return {
            "attempts": [
                {
                    "action": r.action,
                    "status": r.status,
                    "detail": r.detail,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                }
                for r in rows
            ],
            "count": len(rows),
        }

    # ------------------------------------------------------------------
    # Execution primitives (BOUNDED - return what-would-happen)
    # ------------------------------------------------------------------
    def execute_retry(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {"retry_scheduled": True, "attempt": args.get("attempt", 1),
                "detail": "Payment retry enqueued"}

    def send_payment_link(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {"payment_link_sent": True, "channel": "email",
                "subject": args.get("subject", ""), "message_body": args.get("message_body", "")}

    def schedule_followup(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {"followup_scheduled": True, "in_days": args.get("in_days", 3)}

    def escalate_to_human(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {"escalated": True, "reason": args.get("reason", "")}

    def record_outcome(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {"outcome_recorded": True, **args}


def recover_case_state(case: RecoveryCase) -> Dict[str, Any]:
    return {
        "amount": case.revenue_at_risk,
        "existing_retries": case.consecutive_failures or 0,
        "contacts_in_7d": case.contact_count or 0,
        "lifetime_value": 0.0,
    }


def deterministic_recovery_probability(context: Dict[str, Any]) -> float:
    """Base recovery-probability estimate from deterministic signals.

    This is a prior used as the case probability before strategy scoring.
    The strategy-level probabilities come from the strategy generator and the
    deterministic optimizer; this function provides an independent sanity
    estimate from customer + failure signals only.
    """
    p = 0.5
    segment = context.get("segment", "standard")
    ltv = float(context.get("lifetime_value", 0.0))
    failures = int(context.get("consecutive_failures", 0))
    reason = (context.get("failure_reason", "") or "").lower()

    if context.get("recurring_customer") or ltv > 50_000:
        p += 0.12
    if segment == "high_value":
        p += 0.08
    if "timeout" in reason or "degradation" in reason:
        p += 0.15
    if "expired" in reason:
        p += 0.2  # trivially remediable
    if "insufficient" in reason or "funds" in reason:
        p += 0.1
    if "declined" in reason or "limit" in reason:
        p -= 0.08
    p -= 0.05 * failures
    return max(0.05, min(0.93, p))