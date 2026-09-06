"""AI Recovery Agent orchestrator — runs the DETECT->DIAGNOSE->DECIDE->RECOVER
loop for a single case, using only the bounded tools.

Flow:
  1. Investigate  (read-only tools)
  2. RAG          (retrieve merchant policy)
  3. Diagnose     (LLM reasoning ONLY)
  4. Propose      (LLM generates candidate strategies ONLY)
  5. Score        (deterministic optimizer: EV = Risk*P - Cost - Friction)
  6. Gate         (stopping rules + policy engine, deterministic)
  7. Execute      (bounded tool, after policy approval)
  8. Measure      (simulated outcome recorded)
  9. Learn        (outcome feeds the learning loop)
"""
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    RecoveryAction,
    RecoveryCase,
    RecoveryOutcome,
    RecoveryStrategy,
    Transaction,
)
from app.modules import policy_engine, rag_service, stopping_rules
from app.modules.strategy_optimizer import ScoredStrategy, score_strategy
from app.services.agent_tools import AgentTools, deterministic_recovery_probability
from app.services.llm_service import llm
from app.services.learning_service import learning

logger = logging.getLogger("revenova.agent")

ACTION_KEY_MAP = {
    "immediate_retry": "execute_retry",
    "delayed_retry": "delayed_retry",
    "alternative_payment": "send_payment_link",
    "payment_method_update": "send_payment_link",
    "human_escalation": "escalate_to_human",
}


class RecoveryAgent:
    def __init__(self, db: Session):
        self.db = db
        self.tools = AgentTools(db)

    # ------------------------------------------------------------------
    def _audit(self, case, agent, decision, reason, policy_checked="", action="", amount=0.0, detail=""):
        row = AuditLog(
            case_id=case.id if case else None,
            agent=agent,
            decision=decision,
            reason=reason,
            policy_checked=policy_checked,
            action=action,
            amount=float(amount or 0.0),
            detail=detail,
        )
        self.db.add(row)
        self.db.flush()

    # ------------------------------------------------------------------
    def _learning_evidence(self) -> Dict[str, Any]:
        return learning.context()

    # ------------------------------------------------------------------
    def run_case(self, case_id: int, execute: bool = True) -> Dict[str, Any]:
        case = self.db.get(RecoveryCase, case_id)
        if not case:
            raise AgentError(f"case {case_id} not found")
        tx = self.db.get(Transaction, case.transaction_id)

        case.contact_count = case.contact_count or 0
        case.consecutive_failures = case.consecutive_failures or 0
        tools = self.tools

        # --- 1. Investigate (read-only tools) ---------------------------
        tools.get_transaction(tx=tx)
        cust = tools.get_customer(customer_id=tx.customer_id if tx else 0)
        tools.get_failure_details(tx.id if tx else 0, tx=tx)
        if cust:
            tools.get_payment_history(cust.get("id", 0))
        tools.get_recovery_history(case_id)

        # --- 2. RAG: retrieve merchant policy ---------------------------
        query = f"{case.leak_type} {case.root_cause} recovery for amount {round(case.revenue_at_risk or 0)}"
        policies = rag_service.retrieve_policies(self.db, query, limit=3)

        # --- 3. Diagnose (LLM reasoning only) ---------------------------
        failure_reason = tx.failure_reason if tx else "unknown"
        diagnosis = llm.diagnose({
            "failure_reason": failure_reason,
            "failure_rate": case.risk_score or 0.05,
            "baseline_rate": 0.05,
            "customers_affected": 1,
            "window_minutes": 60,
            "recurring_customer": bool(cust and cust.get("lifetime_value", 0.0) > 50_000),
            "prior_successes": (self.db.query(Transaction)
                                .filter(Transaction.customer_id == (tx.customer_id if tx else 0),
                                        Transaction.status == "succeeded").count()),
        })
        case.root_cause = case.root_cause or diagnosis["root_cause"]
        case.confidence = diagnosis["confidence"]
        self._audit(case, "diagnosis", "root_cause_diagnosed",
                    f"{diagnosis['root_cause']} (confidence {diagnosis['confidence']:.0%})",
                    action="diagnose")

        # --- 4. Generate candidate strategies (LLM proposes only) --------
        historical = self._learning_evidence()
        candidates = llm.strategies({
            "root_cause": case.root_cause,
            "failure_reason": failure_reason,
            "amount": round(case.revenue_at_risk or 0, 2),
            "customer_segment": cust.get("segment", "standard") if cust else "standard",
            "historical_recovery": historical,
        })
        strategies: List[ScoredStrategy] = []
        for c in candidates:
            s = score_strategy(
                c, case.revenue_at_risk or 0.0,
                predicted_recovery=c.get("predicted_recovery"),
                intervention_cost=c.get("intervention_cost"),
                friction_cost=c.get("friction_cost"),
                name=c.get("name"), key=c.get("key"),
                cost_tier=c.get("cost_tier"), message=c.get("message"),
            )
            strategies.append(s)
            self._persist_strategy(case, s, AI_proposed=bool(c.get("AI_proposed")))

        best = max(strategies, key=lambda s: s.expected_value) if strategies else None

        # --- 5. Deterministic recovery probability -----------------------
        prob_ctx = {
            "recurring_customer": bool(cust),
            "segment": cust.get("segment", "standard") if cust else "standard",
            "lifetime_value": cust.get("lifetime_value", 0.0) if cust else 0.0,
            "consecutive_failures": case.consecutive_failures,
            "failure_reason": failure_reason,
        }
        case.recovery_probability = round(deterministic_recovery_probability(prob_ctx), 3)

        # --- 6. Stopping rules (deterministic) ---------------------------
        stop = stopping_rules.should_stop(
            consecutive_failures=case.consecutive_failures,
            recovery_probability=case.recovery_probability,
            contacts_in_7d=case.contact_count,
        )
        if stop.should_stop:
            case.status = "stopped"
            self.db.commit()
            self._audit(case, "stopping_rule", "recovery_stopped", stop.reason, action="stop")
            return self._result(case, best, strategies, policies, stop.to_dict())

        # --- 7. Policy validation of recommended action ------------------
        action_key = ACTION_KEY_MAP.get(best.key, best.key) if best else "no_action"
        policy_context = {
            "amount": case.revenue_at_risk or 0.0,
            "existing_retries": case.consecutive_failures,
            "contacts_in_7d": case.contact_count,
            "lifetime_value": cust.get("lifetime_value", 0.0) if cust else 0.0,
        }
        policy_result = policy_engine.evaluate_action(action_key, policy_context)

        if best:
            self._audit(
                case, "ai_agent", "strategy_selected",
                f"Selected {best.name} (EV ₹{best.expected_value:,.0f} = p {best.predicted_recovery:.0%} x risk "
                f"₹{best.revenue_at_risk:,.0f} - cost ₹{best.intervention_cost:,.0f} - friction ₹{best.friction_cost:,.0f})",
                policy_checked=policy_result.rule or "",
                action=action_key,
            )

        if not execute:
            case.status = "open"
            self.db.commit()
            return self._result(case, best, strategies, policies, stop.to_dict(), policy_result)

        # --- 8. Execute through the bounded tool -------------------------
        action_row = self._persist_action(case, best, action_key, policy_result) if best else None
        exec_result = self._execute_tool(case, best, action_key, policy_result, cust, action_row, tx)
        case.status = "recovered" if exec_result.get("success") else "open"
        self.db.commit()
        self._audit(case, "ai_agent", "action_executed", exec_result.get("detail", ""),
                    policy_checked=action_row.policy_checked if action_row else "",
                    action=action_key, amount=exec_result.get("recovered", 0.0))

        # --- 9. Measure + learn ------------------------------------------
        outcome = {}
        if action_row and exec_result.get("measured", True):
            outcome = self._simulate_outcome(case, best, action_row, exec_result)
            self._persist_outcome(case, action_row, best, outcome)
            self._audit(case, "outcome_tracker", "outcome_recorded",
                        f"Predicted {best.predicted_recovery:.0%} -> Actual "
                        f"{'success' if outcome['success'] else 'failure'}; recovered "
                        f"₹{outcome['amount_recovered']:,.0f}",
                        policy_checked=action_row.policy_checked, action=action_key,
                        amount=outcome["amount_recovered"])
            learning.record(best.key, success=outcome["success"])
            case.status = "recovered" if outcome["success"] else case.status
            self.db.commit()

        return self._result(case, best, strategies, policies, stop.to_dict(), policy_result, outcome)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def _persist_strategy(self, case, s: ScoredStrategy, AI_proposed: bool = False):
        row = RecoveryStrategy(
            case_id=case.id,
            strategy=s.key,
            predicted_recovery=round(min(1.0, max(0.0, s.predicted_recovery)), 3),
            cost=s.intervention_cost,
            friction_score=s.friction_cost,
            expected_value=round(s.expected_value, 2),
            is_AI_proposed=AI_proposed,
            recommended=False,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _persist_action(self, case, best: ScoredStrategy, action_key: str, policy_result) -> RecoveryAction:
        strategy = (
            self.db.query(RecoveryStrategy)
            .filter(RecoveryStrategy.case_id == case.id, RecoveryStrategy.strategy == best.key)
            .order_by(RecoveryStrategy.id.desc())
            .first()
        )
        row = RecoveryAction(
            case_id=case.id,
            strategy_id=strategy.id if strategy else None,
            action=action_key,
            tool=f"agent_{action_key}",
            status="executed",
            predicted_recovery=best.predicted_recovery,
            policy_checked=policy_result.rule or "",
            policy_result=policy_result.status,
            detail=f"Policy {policy_result.status}; executing {action_key}",
        )
        self.db.add(row)
        self.db.flush()
        return row

    # ------------------------------------------------------------------
    def _execute_tool(self, case, best, action_key, policy_result, cust, action_row, tx) -> Dict[str, Any]:
        if not policy_result.allowed:
            if action_row:
                action_row.status = "blocked"
            self.db.commit()
            return {"success": False, "detail": f"Blocked by policy: {policy_result.message}",
                    "recovered": 0.0, "measured": True}

        if action_key in ("execute_retry", "delayed_retry"):
            case.consecutive_failures += 1
            res = self.tools.execute_retry({"attempt": case.consecutive_failures})
            # Simulated retry: fails for expired cards / third failure (stopping).
            ok = best.key == "delayed_retry" and "expired" not in (case.root_cause or "").lower()
            return {"success": ok, "detail": res["detail"],
                    "recovered": case.revenue_at_risk if ok else 0.0, "measured": True}

        if action_key == "send_payment_link":
            msg = self.tools.generate_customer_message({
                "action": "payment_method_update" if best.key == "payment_method_update" else "send_payment_link",
                "customer_name": cust.get("name", "there") if cust else "there",
                "amount": case.revenue_at_risk or 0.0,
                "payment_method": tx.payment_method if tx else "card",
                "failure_reason": tx.failure_reason if tx else "",
            })
            self.tools.send_payment_link({"subject": msg.get("subject", ""), "message_body": msg.get("body", "")})
            case.contact_count += 1
            self.db.commit()
            # Simulated: payment link for expired card gets recovered (demo flow).
            ok = "expired" in (case.root_cause or "").lower() or best.key == "alternative_payment"
            return {"success": True, "detail": f"Payment link sent",
                    "recovered": 0.0, "measured": True, "pending_recovery": case.revenue_at_risk,
                    "message_subject": msg.get("subject", ""), "message_body": msg.get("body", "")}

        if action_key in ("escalate_to_human", "human_escalation", "escalate"):
            self.tools.escalate_to_human({"reason": best.name, "case": case.case_code})
            case.status = "escalated"
            self.db.commit()
            return {"success": False, "detail": f"Escalated to human: {best.name}",
                    "recovered": 0.0, "measured": True}

        if action_key in ("stop", "stop_recovery"):
            case.status = "stopped"
            self.db.commit()
            return {"success": False, "detail": "Recovery stopped", "recovered": 0.0, "measured": True}

        return {"success": False, "detail": f"Unknown action {action_key}", "recovered": 0.0, "measured": True}

    # ------------------------------------------------------------------
    def _simulate_outcome(self, case, best, action_row, exec_result) -> Dict[str, Any]:
        """Simulate the actual recovery outcome for a case.

        Deterministic given the scenario so the demo is reproducible; the
        probability used is the strategy's predicted recovery so the learning
        loop sees realistic predicted-vs-actual deltas.
        """
        import random

        rng = random.Random(int(case.id * 7 + 13))
        prob = best.predicted_recovery
        if exec_result.get("recovered", 0.0) > 0 and exec_result.get("success"):
            success, recovered = True, case.revenue_at_risk
        elif exec_result.get("pending_recovery"):
            success = rng.random() < prob
            recovered = case.revenue_at_risk if success else 0.0
        else:
            success = False
            recovered = exec_result.get("recovered", 0.0) or 0.0
        return {
            "success": bool(success),
            "amount_recovered": round(recovered, 2),
            "predicted_recovery": best.predicted_recovery,
            "recovery_time": rng.randint(5, 240) if success else 0,
        }

    def _persist_outcome(self, case, action_row, best, outcome) -> RecoveryOutcome:
        row = RecoveryOutcome(
            action_id=action_row.id,
            case_id=case.id,
            predicted_recovery=best.predicted_recovery,
            amount_recovered=outcome["amount_recovered"],
            success=outcome["success"],
            recovery_time=outcome.get("recovery_time", 0),
        )
        self.db.add(row)
        self.db.flush()
        return row

    # ------------------------------------------------------------------
    def _result(self, case, best, strategies, policies, stop=None, policy_result=None, outcome=None) -> Dict[str, Any]:
        return {
            "case": {
                "id": case.id,
                "case_code": case.case_code,
                "status": case.status,
                "revenue_at_risk": case.revenue_at_risk,
                "root_cause": case.root_cause,
                "confidence": case.confidence,
                "recovery_probability": case.recovery_probability,
                "contact_count": case.contact_count,
                "consecutive_failures": case.consecutive_failures,
            },
            "strategies": [s.to_dict() for s in strategies],
            "best": best.to_dict() if best else None,
            "policies_retrieved": [p.policy_code for p in policies],
            "stopping": stop or {"should_stop": False},
            "policy_result": policy_result.to_dict() if policy_result else None,
            "outcome": outcome,
            "trace": [t.to_dict() for t in self.tools.trace],
        }


class AgentError(Exception):
    pass