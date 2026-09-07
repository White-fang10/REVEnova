"""Unit tests for the deterministic Policy Engine.

These are pure-function tests — no database, no LLM. The engine must return
exactly the same verdict for the same inputs regardless of environment.
"""
import pytest

from app.modules import policy_engine
from app.modules.policy_engine import (
    check_amount_approval,
    check_contact_frequency,
    check_discount,
    check_high_value_escalation,
    check_retry_limit,
    evaluate_action,
)


def test_amount_below_threshold_allowed():
    assert check_amount_approval(99_999)["passed"] is True


def test_amount_above_threshold_requires_approval():
    res = check_amount_approval(101_000)
    assert res["passed"] is False
    assert res["requires_human_approval"] is True
    assert res["rule_id"] == "R01"


def test_amount_exactly_at_threshold_allowed():
    assert check_amount_approval(100_000)["passed"] is True


def test_retry_within_limit_allowed():
    assert check_retry_limit(0)["passed"] is True
    assert check_retry_limit(1)["passed"] is True  # 0-based: 2-run cap


def test_retry_at_limit_blocked():
    res = check_retry_limit(2)
    assert res["passed"] is False
    assert res["rule_id"] == "R02"


def test_discount_within_cap_allowed():
    assert check_discount(9.5)["passed"] is True
    assert check_discount(10.0)["passed"] is True


def test_discount_above_cap_needs_approval():
    res = check_discount(15.0)
    assert res["passed"] is False
    assert res["requires_human_approval"] is True
    assert res["rule_id"] == "R03"


def test_contact_limit():
    assert check_contact_frequency(0)["passed"] is True
    assert check_contact_frequency(2)["passed"] is True
    res = check_contact_frequency(3)
    assert res["passed"] is False
    assert res["rule_id"] == "R04"


def test_high_value_customer_escalation_eligible():
    res = check_high_value_escalation(500_000)
    assert res["passed"] is True
    res2 = check_high_value_escalation(5_000)
    assert res2["passed"] is False


def test_evaluate_retry_allowed():
    res = evaluate_action("execute_retry", {"amount": 50_000, "existing_retries": 0})
    assert res.allowed is True
    assert res.status == "allowed"


def test_evaluate_retry_blocked_by_count():
    res = evaluate_action("execute_retry", {"amount": 50_000, "existing_retries": 2})
    assert res.allowed is False
    assert res.status == "blocked"
    assert res.rule_id == "R02"


def test_evaluate_large_amount_needs_approval():
    res = evaluate_action(
        "execute_retry", {"amount": 1_500_000, "existing_retries": 0}
    )
    assert res.allowed is False
    assert res.status == "approval_required"
    assert res.rule_id == "R01"


def test_evaluate_discount_blocked():
    res = evaluate_action("offer_discount", {"amount": 2_000, "discount_pct": 20})
    assert res.allowed is False
    assert res.rule_id == "R03"


def test_evaluate_contact_over_limit_blocked():
    res = evaluate_action(
        "send_payment_link", {"amount": 2_000, "contacts_in_7d": 3}
    )
    assert res.allowed is False
    assert res.rule_id == "R04"


def test_unknown_action_fails_closed():
    res = evaluate_action("some_weird_action", {"amount": 100})
    assert res.allowed is False
    assert res.message  # empty message would be a silent failure


def test_bookkeeping_always_allowed():
    res = evaluate_action("record_outcome", {"amount": 1_000_000})
    assert res.allowed is True


def test_determinism_across_runs():
    ctx = {"amount": 12_000, "existing_retries": 1, "contacts_in_7d": 1, "lifetime_value": 60_000}
    a = evaluate_action("send_payment_link", ctx)
    b = evaluate_action("send_payment_link", ctx)
    assert a.to_dict() == b.to_dict()