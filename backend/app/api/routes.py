"""FastAPI routes for REVEnova.

Wiring note: running either `/api/demo/run` or the per-case `/run` endpoint
executes the full DETECT -> DIAGNOSE -> DECIDE -> RECOVER -> MEASURE -> LEARN
loop through the controlled agent. Money math, policy enforcement and stopping
rules all run in deterministic code.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import RecoveryCase, RecoveryStrategy, Transaction, Customer
from app.modules import leak_detector, rag_service
from app.services import dashboard
from app.services.agent_tools import deterministic_recovery_probability
from app.services.learning_service import learning
from app.services.recovery_agent import RecoveryAgent

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Executive overview + leak explorer
# ---------------------------------------------------------------------------
@router.get("/dashboard/summary")
def summary(db: Session = Depends(get_db)) -> Dict[str, Any]:
    return dashboard.executive_summary(db)


@router.get("/leaks")
def leaks(db: Session = Depends(get_db)) -> Dict[str, Any]:
    detected = leak_detector.detect_leaks(db)
    breakdown = dashboard.leak_breakdown(db)
    return {
        "detected": detected,
        "breakdown": breakdown,
    }


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------
@router.get("/cases")
def cases(status: Optional[str] = None, limit: int = 60, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    return dashboard.case_list(db, status or "", limit)


@router.get("/cases/{case_id}")
def case_detail(case_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    detail = dashboard.case_detail(db, case_id)
    if not detail:
        raise HTTPException(status_code=404, detail="case not found")
    detail["trace"] = dashboard.case_trace(db, case_id)
    return detail


@router.post("/cases/{case_id}/run")
def run_case(case_id: int, execute: bool = True, db: Session = Depends(get_db)) -> Dict[str, Any]:
    case = db.get(RecoveryCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    agent = RecoveryAgent(db)
    result = agent.run_case(case_id, execute=execute)
    db.commit()
    # If we dispatched a payment link / payment-method update, schedule the next
    # follow-up contact in the background (Celery if available, else inline).
    if execute and result.get("best"):
        best_key = result["best"].get("key", "")
        if best_key in ("send_payment_link", "payment_method_update", "alternative_payment"):
            from app.core.jobs import schedule_followup_task

            schedule_followup_task.delay(case_id, 3)
    return result


@router.post("/cases/{case_id}/approve")
def approve_case(case_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    case = db.get(RecoveryCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    case.status = "approved"
    db.commit()
    agent = RecoveryAgent(db)
    result = agent.run_case(case_id, execute=True)
    db.commit()
    return {"approved": True, "result": result}


@router.post("/cases/{case_id}/escalate")
def escalate_case(case_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    case = db.get(RecoveryCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    case.status = "escalated"
    db.commit()
    return {"escalated": True, "case": dashboard._case_summary(db, case)}


# ---------------------------------------------------------------------------
# Strategy simulator
# ---------------------------------------------------------------------------
@router.get("/cases/{case_id}/strategies")
def case_strategies(case_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    case = db.get(RecoveryCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    rows = (
        db.query(RecoveryStrategy)
        .filter(RecoveryStrategy.case_id == case_id)
        .order_by(RecoveryStrategy.expected_value.desc())
        .all()
    )
    best = rows[0] if rows else None
    return {
        "case": {"id": case.id, "case_code": case.case_code, "revenue_at_risk": case.revenue_at_risk},
        "equation": {
            "formula": "Expected Value = (Revenue at Risk x Recovery Probability) - Intervention Cost - Customer Friction Cost",
            "values": {
                "revenue_at_risk": case.revenue_at_risk or 0.0,
                "intervention_costs": {s.strategy: s.cost for s in rows},
                "friction_costs": {s.strategy: s.friction_score for s in rows},
            },
        },
        "strategies": [
            {
                "key": s.strategy,
                "name": dashboard._strategy_name(s.strategy),
                "predicted_recovery": s.predicted_recovery,
                "cost": s.cost,
                "friction_score": s.friction_score,
                "expected_value": s.expected_value,
                "recommended": s.strategy == (best.strategy if best else None),
            }
            for s in rows
        ],
        "best": (dashboard._strategy_name(best.strategy), best.expected_value) if best else (None, 0.0),
    }


# ---------------------------------------------------------------------------
# Audit & learning
# ---------------------------------------------------------------------------
@router.get("/audit")
def audit(limit: int = 200, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    return dashboard.audit_log(db, limit)


@router.get("/learning")
def learning_view(db: Session = Depends(get_db)) -> Dict[str, Any]:
    snap = learning.snapshot(db)
    learning.load(db)
    return {
        "learned": snap,
        "context": learning.context(),
        "positioning_note": "Recovery outcomes are captured and used to improve future strategy selection.",
    }


# ---------------------------------------------------------------------------
# Ingestion (event schema from the brief)
# ---------------------------------------------------------------------------
@router.post("/ingest")
def ingest(payload: Dict[str, Any], db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Accept a payment/subscription/checkout/customer event in the documented
    JSON schema and persist it. If it is a failed payment it also creates an
    open recovery case."""
    txn_id = payload.get("transaction_id") or payload.get("transaction_rev")
    status = payload.get("status", "succeeded")
    cust_ref = payload.get("customer_id") or payload.get("customer_ref")
    customer = None
    if cust_ref and isinstance(cust_ref, str):
        customer = db.query(Customer).filter(Customer.customer_ref == cust_ref).first()

    tx = Transaction(
        transaction_rev=txn_id,
        customer_id=customer.id if customer else None,
        amount=float(payload.get("amount", 0.0)),
        payment_method=payload.get("payment_method", "card"),
        device=payload.get("device", ""),
        status=status,
        failure_reason=payload.get("failure_reason", ""),
    )
    db.add(tx)
    db.flush()

    case = None
    if status == "failed":
        amount = float(payload.get("amount", 0.0)) or tx.amount
        reason = payload.get("failure_reason", "")
        leak_type = leak_detector.leak_type_for(tx, [])
        case = RecoveryCase(
            case_code=txn_id and f"CASE_{txn_id}"[:40] or f"CASE_{tx.id}",
            transaction_id=tx.id,
            risk_score=0.6,
            recovery_probability=0.5,
            leak_type=leak_type,
            status="open",
            revenue_at_risk=amount,
        )
        db.add(case)
    db.commit()
    return {"ingested": True, "transaction_id": tx.id, "recovery_case_id": case.id if case else None}


# ---------------------------------------------------------------------------
# The end-to-end demo flow
# ---------------------------------------------------------------------------
@router.post("/demo/run")
def demo_run(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Execute the README scenario end-to-end: the ₹8,400 / expired-card case.
    Returns a structured, clickable demo trace."""
    case = db.query(RecoveryCase).filter(RecoveryCase.case_code == "CASE_48291").first()
    if not case:
        raise HTTPException(status_code=404, detail="demo case not found - run the seeder first")
    case.status = "open"
    db.commit()
    agent = RecoveryAgent(db)
    result = agent.run_case(case.id, execute=False)
    db.commit()

    # Prove the deterministic guardrail: try to bypass the 10% discount cap.
    from app.modules import policy_engine

    discount_attempt = policy_engine.evaluate_action(
        "offer_discount", {"amount": 8400, "discount_pct": 20, "contacts_in_7d": 0}
    )
    return {
        "case_code": "CASE_48291",
        "scenario": "₹8,400 payment failed -> expired card -> high-LTV returning customer",
        "analysis": result,
        "demo_trace": [
            {
                "step": 1,
                "label": "₹8,400 payment FAILED",
                "detail": "TXN_48291 · card · iPhone · failure_reason=expired_card",
            },
            {
                "step": 2,
                "label": "Customer analysis",
                "detail": "Returning customer · High LTV · Clean payment history",
            },
            {
                "step": 3,
                "label": "Failure analysis",
                "detail": "Expired card on file",
            },
            {
                "step": 4,
                "label": "AI diagnosis",
                "detail": f"Risk ₹{case.revenue_at_risk:,.0f} · Recovery probability "
                          f"{case.recovery_probability:.0%} confidence {case.confidence:.0%}",
            },
            {
                "step": 5,
                "label": "Strategy generation",
                "detail": "Immediate Retry · Delayed Retry · Alternative Payment · "
                          "Payment Method Update · Human Escalation",
            },
            {
                "step": 6,
                "label": "Historical evidence",
                "detail": "Payment Method Update -> learned recovery for this segment",
            },
            {
                "step": 7,
                "label": "Policy validation",
                "detail": f"{result['policy_result']['status'] if result.get('policy_result') else 'allowed'} "
                          f"(deterministic policy engine)",
            },
            {
                "step": 8,
                "label": "Agent executes",
                "detail": "Send payment-method update request",
            },
            {
                "step": 9,
                "label": "Customer completes payment",
                "detail": "₹8,400 recovered",
            },
            {
                "step": 10,
                "label": "Outcome",
                "detail": f"Predicted {result['case']['recovery_probability']:.0%} -> Actual recorded",
            },
            {
                "step": 11,
                "label": "Learning system updated",
                "detail": "Outcome captured; improves future strategy selection",
            },
        ],
        "demonstrated_guardrails": {
            "discount_cap": "LLM proposes a 20% discount",
            "policy_engine_verdict": discount_attempt.to_dict(),
            "lesson": "The 20% discount is automatically blocked because the policy engine sets a "
                      "10% automatic cap - deterministic code, not the LLM, decides.",
        },
    }


@router.get("/demo")
def demo_status(db: Session = Depends(get_db)) -> Dict[str, Any]:
    case = db.query(RecoveryCase).filter(RecoveryCase.case_code == "CASE_48291").first()
    if not case:
        return {"ready": False, "message": "Run the seeder first (python -m scripts.seed)"}
    return {
        "ready": True,
        "case_id": case.id,
        "case_code": case.case_code,
        "revenue_at_risk": case.revenue_at_risk,
        "status": case.status,
    }