"""Recovery Strategy Optimizer — deterministic value scoring.

The LLM only *proposes* candidate strategies. This module computes the
expected value of each candidate deterministically and selects the optimum:

    Expected Value = (Revenue at Risk × Recovery Probability)
                     − Intervention Cost − Customer Friction Cost

Selection rule: highest expected value, NOT highest raw probability. Pure,
testable, no LLM.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ScoredStrategy:
    key: str
    name: str
    predicted_recovery: float
    expected_value: float
    intervention_cost: float
    friction_cost: float
    cost_tier: str
    revenue_at_risk: float
    message: Optional[str] = None
    AI_proposed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "predicted_recovery": self.predicted_recovery,
            "expected_value": round(self.expected_value, 2),
            "intervention_cost": self.intervention_cost,
            "friction_cost": self.friction_cost,
            "cost_tier": self.cost_tier,
            "revenue_at_risk": self.revenue_at_risk,
            "message": self.message,
            "AI_proposed": self.AI_proposed,
        }


def score_strategy(
    candidate: Dict[str, Any],
    revenue_at_risk: float,
    *,
    predicted_recovery: Optional[float] = None,
    intervention_cost: Optional[float] = None,
    friction_cost: Optional[float] = None,
    name: Optional[str] = None,
    key: Optional[str] = None,
    cost_tier: Optional[str] = None,
    message: Optional[str] = None,
) -> ScoredStrategy:
    """Score a single candidate strategy deterministically."""
    prob = (predicted_recovery if predicted_recovery is not None else candidate.get("predicted_recovery", 0.0)) or 0.0
    p_cost = intervention_cost if intervention_cost is not None else candidate.get("intervention_cost", 0.0)
    f_cost = friction_cost if friction_cost is not None else candidate.get("friction_cost", 0.0)
    expected = (revenue_at_risk * prob) - p_cost - f_cost

    return ScoredStrategy(
        key=str(key or candidate.get("key", "strategy")),
        name=str(name or candidate.get("name", "Strategy")),
        predicted_recovery=float(prob),
        expected_value=float(expected),
        intervention_cost=float(p_cost),
        friction_cost=float(f_cost),
        cost_tier=str(cost_tier or candidate.get("cost_tier", "low")),
        revenue_at_risk=float(revenue_at_risk),
        message=message if message is not None else candidate.get("message"),
        AI_proposed=bool(candidate.get("AI_proposed", False)),
    )


def select_best(candidates: List[Dict[str, Any]], revenue_at_risk: float) -> ScoredStrategy:
    """Score all candidates and return the highest expected value."""
    scored = [score_strategy(c, revenue_at_risk) for c in candidates]
    if not scored:
        # No strategy could be generated — nothing profitable to do.
        return ScoredStrategy(
            key="no_action",
            name="No Action",
            predicted_recovery=0.0,
            expected_value=0.0,
            intervention_cost=0.0,
            friction_cost=0.0,
            cost_tier="none",
            revenue_at_risk=float(revenue_at_risk),
            message="No candidate strategy could be generated; case requires human review.",
        )
    return max(scored, key=lambda s: s.expected_value)


def score_all(candidates: List[Dict[str, Any]], revenue_at_risk: float) -> List[ScoredStrategy]:
    if not candidates:
        return []
    return [score_strategy(c, revenue_at_risk) for c in candidates]