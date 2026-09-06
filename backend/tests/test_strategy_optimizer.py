"""Tests for the deterministic strategy optimizer."""
import pytest

from app.modules.strategy_optimizer import score_all, score_strategy, select_best


CANDIDATES = [
    {"key": "immediate_retry", "name": "Immediate Retry", "predicted_recovery": 0.31,
     "intervention_cost": 2.0, "friction_cost": 1.0, "cost_tier": "low"},
    {"key": "delayed_retry", "name": "Delayed Retry", "predicted_recovery": 0.47,
     "intervention_cost": 2.0, "friction_cost": 1.0, "cost_tier": "low"},
    {"key": "alternative_payment", "name": "Alternative Payment Method", "predicted_recovery": 0.62,
     "intervention_cost": 12.0, "friction_cost": 6.0, "cost_tier": "medium"},
    {"key": "human_escalation", "name": "Human Escalation", "predicted_recovery": 0.71,
     "intervention_cost": 150.0, "friction_cost": 25.0, "cost_tier": "high"},
]


def test_expected_value_formula():
    s = score_strategy(CANDIDATES[0], revenue_at_risk=482_000)
    # EV = 482000 * 0.31 - 2 - 1 = 149417
    assert s.expected_value == pytest.approx(149_417.0)


def test_best_is_not_highest_raw_probability():
    """Human Escalation has the highest raw probability (0.71) but its high
    cost makes it lose to Alternative Payment (EV 298,822 vs 166,767)."""
    best = select_best(CANDIDATES, revenue_at_risk=482_000)
    assert best.key == "alternative_payment"


def test_score_all_order():
    scored = score_all(CANDIDATES, revenue_at_risk=482_000)
    values = [s.expected_value for s in scored]
    assert values == sorted(values, reverse=True)


def test_select_best_empty_returns_no_action():
    best = select_best([], revenue_at_risk=1000)
    assert best.key == "no_action"