"""Dashboard aggregation service — powers the five frontend views.

Pure read-side queries over the ORM. All money math is deterministic here;
this layer never delegates a financial figure to the LLM.
"""
from typing import Any, Dict, List

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Customer,
    RecoveryAction,
    RecoveryCase,
    RecoveryOutcome,
    RecoveryStrategy,
    Transaction,
)


def executive_summary(db: Session) -> Dict[str, Any]:
    open_cases = db.query(RecoveryCase).filter(RecoveryCase.status == "open").all()
    active_cases = db.query(RecoveryCase).filter(
        RecoveryCase.status.in_(["open", "approved", "escalated"])
    ).all()

    # Historically at-risk revenue = revenue_at_risk across ALL cases.
    all_cases = db.query(RecoveryCase).all()
    total_at_risk_all = sum(c.revenue_at_risk or 0.0 for c in all_cases)

    active_revenue_at_risk = sum(c.revenue_at_risk or 0.0 for c in active_cases)
    predicted_recovery_active = sum(
        (c.revenue_at_risk or 0.0) * (c.recovery_probability or 0.0) for c in active_cases
    )

    total_recovered = (
        db.query(func.coalesce(func.sum(RecoveryOutcome.amount_recovered), 0.0)).scalar() or 0.0
    )
    predicted_recovery_all = sum(
        (c.revenue_at_risk or 0.0) * (c.recovery_probability or 0.0) for c in all_cases
    )

    recovery_rate = (total_recovered / total_at_risk_all) if total_at_risk_all else 0.0

    case_counts = {
        "total": len(all_cases),
        "open": len(open_cases),
        "recovered": db.query(RecoveryCase).filter(RecoveryCase.status == "recovered").count(),
        "escalated": db.query(RecoveryCase).filter(RecoveryCase.status == "escalated").count(),
        "closed": db.query(RecoveryCase).filter(RecoveryCase.status == "closed").count(),
        "stopped": db.query(RecoveryCase).filter(RecoveryCase.status == "stopped").count(),
    }

    return {
        "currency": "INR",
        # Active (what's currently at risk and actionable)
        "active_revenue_at_risk": round(active_revenue_at_risk, 2),
        "predicted_recovery_active": round(predicted_recovery_active, 2),
        "active_cases": len(active_cases),
        # Lifetime roll-up (measured, most important metric = actual money back)
        "revenue_at_risk": round(total_at_risk_all, 2),
        "predicted_recovery": round(predicted_recovery_all, 2),
        "actual_recovery": round(total_recovered, 2),
        "recovery_rate": round(recovery_rate, 4),
        "case_counts": case_counts,
        "learned_strategy_count": db.query(RecoveryStrategy).filter(RecoveryStrategy.recommended.is_(True)).count(),
    }


def leak_breakdown(db: Session) -> List[Dict[str, Any]]:
    cases = db.query(RecoveryCase).filter(
        RecoveryCase.status.in_(["open", "approved", "escalated"])
    ).all()
    buckets: Dict[str, Dict[str, float]] = {}
    for c in cases:
        lt = c.leak_type or "Other"
        b = buckets.setdefault(lt, {"revenue_at_risk": 0.0, "count": 0.0, "predicted_recovery": 0.0})
        b["revenue_at_risk"] += c.revenue_at_risk or 0.0
        b["count"] += 1
        b["predicted_recovery"] += (c.revenue_at_risk or 0.0) * (c.recovery_probability or 0.0)
    out = []
    for lt, b in buckets.items():
        out.append({
            "type": lt,
            "revenue_at_risk": round(b["revenue_at_risk"], 2),
            "cases": int(b["count"]),
            "predicted_recovery": round(b["predicted_recovery"], 2),
        })
    out.sort(key=lambda x: x["revenue_at_risk"], reverse=True)
    # Always include server-side lea| detection output too.
    return out


def case_list(db: Session, status: str = "", limit: int = 60) -> List[Dict[str, Any]]:
    q = db.query(RecoveryCase)
    if status:
        q = q.filter(RecoveryCase.status == status)
    cases = q.order_by(RecoveryCase.created_at.desc()).limit(limit).all()
    return [_case_summary(db, c) for c in cases]


def _case_summary(db: Session, c: RecoveryCase) -> Dict[str, Any]:
    tx = db.get(Transaction, c.transaction_id) if c.transaction_id else None
    cust = db.get(Customer, tx.customer_id) if tx and tx.customer_id else None
    best = (
        db.query(RecoveryStrategy)
        .filter(RecoveryStrategy.case_id == c.id)
        .order_by(RecoveryStrategy.expected_value.desc())
        .first()
    )
    return {
        "id": c.id,
        "case_code": c.case_code,
        "status": c.status,
        "revenue_at_risk": c.revenue_at_risk,
        "recovery_probability": c.recovery_probability,
        "root_cause": c.root_cause,
        "confidence": c.confidence,
        "leak_type": c.leak_type,
        "customer": cust.name if cust else None,
        "customer_segment": cust.segment if cust else None,
        "payment_method": tx.payment_method if tx else None,
        "failure_reason": tx.failure_reason if tx else None,
        "transaction_ref": tx.transaction_rev if tx else None,
        "recommended_strategy": best.strategy if best else None,
        "best_expected_value": best.expected_value if best else 0.0,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def case_detail(db: Session, case_id: int) -> Dict[str, Any]:
    c = db.get(RecoveryCase, case_id)
    if not c:
        return {}
    tx = db.get(Transaction, c.transaction_id) if c.transaction_id else None
    cust = db.get(Customer, tx.customer_id) if tx and tx.customer_id else None

    strategies = (
        db.query(RecoveryStrategy)
        .filter(RecoveryStrategy.case_id == case_id)
        .order_by(RecoveryStrategy.expected_value.desc())
        .all()
    )
    actions = (
        db.query(RecoveryAction)
        .filter(RecoveryAction.case_id == case_id)
        .order_by(RecoveryAction.timestamp)
        .all()
    )
    details = {
        **(_case_summary(db, c)),
        "customer": {
            "name": cust.name if cust else None,
            "segment": cust.segment if cust else None,
            "lifetime_value": cust.lifetime_value if cust else 0.0,
            "payment_method": cust.payment_method if cust else None,
        },
        "transaction": {
            "amount": tx.amount if tx else 0.0,
            "payment_method": tx.payment_method if tx else None,
            "device": tx.device if tx else None,
            "status": tx.status if tx else None,
            "failure_reason": tx.failure_reason if tx else None,
            "transaction_ref": tx.transaction_rev if tx else None,
            "timestamp": tx.timestamp.isoformat() if tx and tx.timestamp else None,
        },
        "strategies": [
            {
                "id": s.id,
                "key": s.strategy,
                "name": _strategy_name(s.strategy),
                "predicted_recovery": s.predicted_recovery,
                "cost": s.cost,
                "friction_score": s.friction_score,
                "expected_value": s.expected_value,
                "recommended": s.recommended,
                "is_AI_proposed": s.is_AI_proposed,
            }
            for s in strategies
        ],
        "actions": [
            {
                "id": a.id,
                "action": a.action,
                "tool": a.tool,
                "status": a.status,
                "predicted_recovery": a.predicted_recovery,
                "policy_checked": a.policy_checked,
                "policy_result": a.policy_result,
                "detail": a.detail,
                "timestamp": a.timestamp.isoformat() if a.timestamp else None,
            }
            for a in actions
        ],
    }
    return details


def _strategy_name(key: str) -> str:
    return {
        "immediate_retry": "Immediate Retry",
        "delayed_retry": "Delayed Retry",
        "alternative_payment": "Alternative Payment Method",
        "payment_method_update": "Payment Method Update",
        "human_escalation": "Human Escalation",
    }.get(key, key)


def audit_log(db: Session, limit: int = 200) -> List[Dict[str, Any]]:
    rows = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "case_id": r.case_id,
            "case_code": db.get(RecoveryCase, r.case_id).case_code if r.case_id and db.get(RecoveryCase, r.case_id) else None,
            "agent": r.agent,
            "decision": r.decision,
            "reason": r.reason,
            "policy_checked": r.policy_checked,
            "action": r.action,
            "amount": r.amount,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        }
        for r in rows
    ]


def case_trace(db: Session, case_id: int) -> List[Dict[str, Any]]:
    """Reconstruct the agent's execution trace for a case from audit rows."""
    return [
        r for r in audit_log(db, 1000)
        if r["case_id"] == case_id
    ]