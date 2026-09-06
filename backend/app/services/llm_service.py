"""LLM interface — reasoning ONLY.

The LLM is allowed to: root-cause diagnose, generate candidate strategies, and
draft customer-facing messages.

It is NEVER the final authority on: money math, permissions, limits, policy
enforcement, or safety. Those live in deterministic modules (policy_engine,
stopping_rules, strategy_optimizer).

When no OPENAI_API_KEY is present the interface falls back to a deterministic
rule-based mock that produces the same *structure* of output (diagnosis with
evidence bullets, candidate strategies with recovery probabilities that then
get re-scored deterministically anyway, and templated customer messages). This
keeps the whole demo runnable with zero external dependencies while preserving
the architectural separation of concerns.
"""
import json
import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger("revenova.llm")


# ---------------------------------------------------------------------------
# Mock (deterministic) LLM
# ---------------------------------------------------------------------------
def _mock_diagnose(context: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic diagnosis generator that mimics LLM output structure.

    It inspects the aggregated failure signals and returns a root cause based
    on which signal is most anomalous. This is NOT the real intelligence — it
    is a deterministic stand-in so the demo works without an API key. When a
    real LLM is configured it is invoked instead.
    """
    failure_reason = context.get("failure_reason", "").lower()
    failure_rate = context.get("failure_rate", 0.0)
    baseline_rate = context.get("baseline_rate", 0.0)
    customers_affected = context.get("customers_affected", 1)
    window_minutes = context.get("window_minutes", 60)
    recurring_customer = context.get("recurring_customer", False)
    prior_successes = context.get("prior_successes", 0)

    evidence: List[str] = []
    root_cause = ""
    confidence = 0.0

    ratio = (failure_rate / baseline_rate) if baseline_rate else 1.0

    if "timeout" in failure_reason or "gateway" in failure_reason or "provider" in failure_reason:
        root_cause = "Payment-channel degradation"
        confidence = min(0.95, 0.62 + 0.3 * (ratio - 1) / 10 + 0.08 * min(customers_affected, 100) / 100)
        evidence = [
            f"Failure rate increased {ratio:.1f}× vs baseline ({baseline_rate:.1%} → {failure_rate:.1%})",
            f"{customers_affected} customers affected within a {window_minutes}-minute window",
            "Cluster of timeouts across a shared payment rail",
            "No per-customer anomaly; histories are normal",
        ]
    elif "expired" in failure_reason:
        root_cause = "Expired card on file"
        confidence = 0.91 if recurring_customer else 0.84
        evidence = [
            "Failure code indicates an expired card (EXPIRED_CARD)",
            "Customer is a recurring payer with clean prior history",
            f"Customer has {prior_successes} successful prior transactions",
            "Remediation = payment-method update (low friction, high historical success)",
        ]
    elif "insufficient" in failure_reason or "funds" in failure_reason:
        root_cause = "Insufficient funds"
        confidence = 0.78 if recurring_customer else 0.71
        evidence = [
            "Decline code INSUFFICIENT_FUNDS",
            "Customer is a returning payer; single-instance issue",
            "Delayed retry historically recovers this pattern well",
        ]
    elif "limit" in failure_reason or "card_not_present" in failure_reason:
        root_cause = "Customer-specific payment restriction"
        confidence = 0.74
        evidence = [
            "Decline indicates a bank-side spending restriction",
            "Customer normally completes payments successfully",
            "Recommend alternative payment method to bypass the restriction",
        ]
    elif "unknown" in failure_reason or "declined" in failure_reason or not failure_reason:
        root_cause = "Generic decline — customer-specific issue"
        confidence = 0.58
        evidence = [
            "Decline is isolated to a single customer",
            "No cohort-level anomaly detected",
            "Alternative payment method is the lowest-risk route to recovery",
        ]
    elif "abandon" in failure_reason or "abandoned" in failure_reason:
        root_cause = "Checkout abandonment"
        confidence = 0.81
        evidence = [
            "Cart created but payment never reached the gateway",
            "Recurring abandonment pattern at the payment step",
            "Recovery intervention = checkout reminder or payment link",
        ]
    else:
        root_cause = "Payment-channel degradation"
        confidence = 0.63
        evidence = [
            f"Elevated failure rate {failure_rate:.1%} vs baseline {baseline_rate:.1%}",
            f"{customers_affected} customers affected",
            "Concentrated failure window suggests a shared-rail problem",
        ]

    return {
        "root_cause": root_cause,
        "confidence": round(min(0.97, confidence), 2),
        "evidence": evidence,
        "kind": "mock",
    }


def _mock_strategies(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Deterministic strategy candidate generator.

    Produces 4 candidate strategies with *baseline* predicted recovery values.
    These are passed to the deterministic optimizer, which re-scores them with
    the formula (Risk × Probability) − Cost − Friction and may blend in
    historical outcome evidence from the learning loop. The mock deliberately
    returns the same anchor values the real LLM would.
    """
    root_cause = context.get("root_cause", "").lower()
    failure_reason = context.get("failure_reason", "").lower()
    historical = context.get("historical_recovery", {}) or {}

    def h(learned_slot: str, default: float) -> float:
        val = historical.get(learned_slot)
        return float(val) if val is not None else default

    strategies: List[Dict[str, Any]] = []

    base_immediate = 0.31
    base_delayed = 0.47
    base_alt = 0.62
    base_escalate = 0.71

    # Blend in learning-loop evidence when available.
    immediate = h("immediate_retry", base_immediate)
    delayed = h("delayed_retry", base_delayed)
    alt = h("alternative_payment", base_alt)
    escalate = h("human_escalation", base_escalate)

    # Adjust for specific root causes.
    if "expired" in root_cause or "expired" in failure_reason:
        # Alternate payment / payment-update performs best for expired cards.
        alt = max(alt, 0.76)
        immediate = min(immediate, 0.05)  # retrying an expired card is pointless
    if "insufficient" in failure_reason:
        delayed = max(delayed, 0.62)  # funds usually appear within days
        immediate = min(immediate, 0.12)
    if "timeout" in failure_reason or "degradation" in root_cause:
        delayed = max(delayed, 0.62)  # degradation resolves; retry later
        immediate = min(immediate, 0.18)
    if "abandon" in failure_reason or "abandon" in root_cause:
        alt = max(alt, 0.68)  # a fresh payment link recovers abandonments well

    strategies.append(_candidate("Immediate Retry", "immediate_retry", immediate, cost_tier="low"))
    strategies.append(_candidate("Delayed Retry", "delayed_retry", delayed, cost_tier="low", delay_days=3))
    strategies.append(_candidate("Alternative Payment Method", "alternative_payment", alt, cost_tier="medium"))
    # Escalation: high raw probability but high cost — the optimizer will decide.
    strategies.append(_candidate("Human Escalation", "human_escalation", escalate, cost_tier="high"))

    # Specialised strategy surfaced only for the expired-card scenario.
    if "expired" in root_cause or "expired" in failure_reason:
        update_p = h("payment_method_update", 0.76)
        strategies.append(
            _candidate(
                "Payment Method Update",
                "payment_method_update",
                update_p,
                cost_tier="low",
                message="Send the customer a secure payment-method update request (card expiry)",
                AI_proposed=True,
            )
        )

    return strategies


def _candidate(name: str, key: str, prob: float, cost_tier: str, **extra: Any) -> Dict[str, Any]:
    costs = {"low": 2.0, "medium": 12.0, "high": 150.0}
    friction = {"low": 1.0, "medium": 6.0, "high": 25.0}
    out: Dict[str, Any] = {
        "name": name,
        "key": key,
        "predicted_recovery": round(float(prob), 3),
        "cost_tier": cost_tier,
        "intervention_cost": costs[cost_tier],
        "friction_cost": friction[cost_tier],
    }
    out.update(extra)
    return out


def _mock_message(context: Dict[str, Any]) -> Dict[str, Any]:
    action = context.get("action", "send_payment_link")
    customer_name = context.get("customer_name", "there")
    amount = context.get("amount", 0.0)
    payment_method = context.get("payment_method", "card")

    if action in ("send_payment_link", "payment_method_update", "send_payment_link"):
        if "expired" in context.get("failure_reason", "").lower() or action == "payment_method_update":
            subject = "Update your payment method — your ₹%s payment is on hold" % f"{amount:,.0f}"
            body = (
                f"Hi {customer_name}, thanks for choosing us. Your recent payment of ₹{amount:,.0f} "
                f"({payment_method}) didn't go through because the card on file has expired. "
                f"Updating your payment method takes less than a minute and we'll retry the charge "
                f"right away."
            )
        else:
            subject = "A secure payment link for your outstanding amount"
            body = (
                f"Hi {customer_name}, here is a secure payment link for ₹{amount:,.0f}. "
                f"You can complete the payment at your convenience."
            )
    elif action in ("execute_retry", "delayed_retry"):
        subject = "We're retrying your payment"
        body = (
            f"Hi {customer_name}, we noticed your recent payment attempt of ₹{amount:,.0f} "
            f"didn't go through. We'll automatically retry it shortly — no action needed."
        )
    elif action == "send_reminder":
        subject = "Your outstanding balance of ₹%s" % f"{amount:,.0f}"
        body = (
            f"Hi {customer_name}, this is a friendly reminder that ₹{amount:,.0f} is still "
            f"outstanding. You can complete it in a couple of taps."
        )
    else:
        subject = "Update needed"
        body = f"Hi {customer_name}, a small update is needed to complete your ₹{amount:,.0f} payment."

    return {
        "subject": subject,
        "body": body,
        "channel": "email",
        "kind": "mock",
    }


# ---------------------------------------------------------------------------
# LLM dispatcher
# ---------------------------------------------------------------------------
def _real_llm(system: str, user: str) -> str:
    """Call the real OpenAI-compatible LLM. Used ONLY for reasoning output."""
    import openai

    client = openai.OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.3,
    )
    return resp.choices[0].message.content or ""


def _parse_json(text: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return None
        return None


class LLMService:
    """Thin facade over the reasoning backend (real LLM or deterministic mock)."""

    def __init__(self) -> None:
        self.mock = settings.use_mock_llm
        if not self.mock:
            try:
                import openai  # noqa: F401
            except ImportError:
                logger.warning("openai not installed -> falling back to mock LLM")
                self.mock = True

    def diagnose(self, context: Dict[str, Any]) -> Dict[str, Any]:
        if self.mock:
            return _mock_diagnose(context)
        system = (
            "You are REVEnova's revenue-leak diagnosis engine. Given payment failure "
            "signals, return strict JSON: {\"root_cause\": string, \"confidence\": 0..1, "
            "\"evidence\": [string]}. Diagnose root cause; never propose actions; never "
            "touch money math."
        )
        user = json.dumps(context)
        text = _real_llm(system, user)
        parsed = _parse_json(text) or {}
        return {
            "root_cause": parsed.get("root_cause") or _mock_diagnose(context)["root_cause"],
            "confidence": float(parsed.get("confidence", 0.7)),
            "evidence": parsed.get("evidence") or [],
            "kind": "llm",
        }

    def strategies(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        if self.mock:
            return _mock_strategies(context)
        system = (
            "You are REVEnova's recovery-strategy generator. Return strict JSON array of 3-5 "
            "candidate strategies with keys: name, key, predicted_recovery (0..1), cost_tier "
            "(low|medium|high), and optional message. Recoveries are baseline estimates only; "
            "the deterministic optimizer re-scores them. Never include monetary totals."
        )
        user = json.dumps(context)
        text = _real_llm(system, user)
        parsed = _parse_json(text)
        if parsed and isinstance(parsed, list):
            return [self._candidate(**{**c, "predicted_recovery": c.get("predicted_recovery", 0.5) if isinstance(c, dict) else 0.5}) for c in parsed[:6]]
        return _mock_strategies(context)

    def _candidate(self, **kw: Any) -> Dict[str, Any]:
        costs = {"low": 2.0, "medium": 12.0, "high": 150.0}
        friction = {"low": 1.0, "medium": 6.0, "high": 25.0}
        tier = kw.get("cost_tier", "low")
        return {
            "name": kw.get("name", "Strategy"),
            "key": kw.get("key", "strategy"),
            "predicted_recovery": float(kw.get("predicted_recovery", 0.5)),
            "cost_tier": tier,
            "intervention_cost": costs.get(tier, 2.0),
            "friction_cost": friction.get(tier, 1.0),
            "message": kw.get("message", None),
        }

    def message(self, context: Dict[str, Any]) -> Dict[str, Any]:
        if self.mock:
            return _mock_message(context)
        system = (
            "You are REVEnova's customer-communication composer. Draft a short, warm, clear "
            "payment-recovery message. Return strict JSON: {\"subject\": string, \"body\": "
            "string, \"channel\": \"email\"}. The recipient is a legitimate customer with an "
            "outstanding trusted balance. No scare tactics, no false claims."
        )
        user = json.dumps(context)
        text = _real_llm(system, user)
        parsed = _parse_json(text) or {}
        return {
            "subject": parsed.get("subject", "Update needed"),
            "body": parsed.get("body", "Thanks for your patience."),
            "channel": parsed.get("channel", "email"),
            "kind": "llm",
        }


llm = LLMService()