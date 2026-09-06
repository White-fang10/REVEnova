"""Revenue Leak Detection — statistical anomaly detection.

Leaks are identified ONLY when a cohort's failure behavior deviates
statistically from its baseline. A single failed transaction is never such a
deviation and is never reported as a systemic leak here.

Detection approach (deterministic, uses numpy):
  1. Group recent failed transactions by cohort dimensions
     (payment_method, failure_reason, or merchant-wide).
  2. Compare current failure rate to the cohort baseline with a
     one-sided z-score / normal-approximation test.
  3. Aggregate the revenue-at-risk from affected transactions.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Transaction

logger = logging.getLogger("revenova.detector")

MIN_TRANSACTIONS = 20       # don't call it a cohort below this size
BASELINE_WINDOW_DAYS = 30   # baseline computed over the prior month
CURRENT_WINDOW_DAYS = 2     # leak window - recent activity
DETECTION_Z = 2.5           # one-sided z-score threshold (approx 99.4% tail)


def _baseline_stats(transactions: List[Transaction]) -> Dict[str, float]:
    if not transactions:
        return {"count": 0, "failure_rate": 0.0, "std": 0.0}
    statuses = [1 if t.status == "failed" else 0 for t in transactions]
    arr = np.array(statuses, dtype=float)
    rate = float(arr.mean())
    return {
        "count": len(transactions),
        "failure_rate": rate,
        "std": float(arr.std(ddof=1)) if len(arr) > 1 else 0.0,
    }


def detect_leaks(
    db: Session,
    window_days: int = CURRENT_WINDOW_DAYS,
    baseline_days: int = BASELINE_WINDOW_DAYS,
    z_threshold: float = DETECTION_Z,
    min_transactions: int = MIN_TRANSACTIONS,
) -> List[Dict[str, Any]]:
    """Scan recent transactions and report cohort-level leaks.

    Returns a list of leak dicts:
        {
          dimension, value, current_rate, baseline_rate, zscore, delta_pts,
          affected_count, revenue_at_risk, transactions: [ids]
        }
    """
    now = datetime.utcnow()
    window_start = now - timedelta(days=window_days)
    baseline_start = now - timedelta(days=baseline_days)

    # 1) Merchant-wide recent transactions.
    recent = (
        db.query(Transaction)
        .filter(Transaction.timestamp >= window_start)
        .order_by(Transaction.timestamp.desc())
        .all()
    )
    if len(recent) < min_transactions:
        logger.info("Not enough recent transactions (%d < %d) to run detection", len(recent), min_transactions)
        return []

    # 2) Merchant-wide baseline (excluding the current window to avoid overlap).
    baseline_rows = (
        db.query(Transaction)
        .filter(Transaction.timestamp >= baseline_start, Transaction.timestamp < window_start)
        .all()
    )

    # At minimum classify the merchant-wide cohort.
    groups: Dict[str, Dict[str, Any]] = {}

    # Leak dimensions:
    def add_group(key: str, label: str, members: List[Transaction]) -> None:
        if len(members) < MIN_TRANSACTIONS:
            return
        baseline_members = [t for t in baseline_rows if _matches(t, key)]
        current = _baseline_stats(members)
        baseline = _baseline_stats(baseline_members)
        if current["count"] < min_transactions:
            return
        zscore = _zscore(current, baseline)
        # Only flag if current rate is meaningfully ABOVE baseline (one-sided).
        if current["failure_rate"] <= baseline["failure_rate"] or zscore < z_threshold:
            return
        delta = current["failure_rate"] - baseline["failure_rate"]
        revenue_at_risk = sum(t.amount for t in members if t.status == "failed")
        groups[key] = {
            "dimension": key.split("::")[0],
            "value": label,
            "current_count": current["count"],
            "current_rate": round(current["failure_rate"], 4),
            "baseline_count": baseline["count"],
            "baseline_rate": round(baseline["failure_rate"], 4),
            "zscore": round(zscore, 2),
            "delta_pts": round(delta * 100, 2),
            "affected_count": sum(1 for t in members if t.status == "failed"),
            "revenue_at_risk": round(revenue_at_risk, 2),
            "rate_multiplier": round(current["failure_rate"] / baseline["failure_rate"], 2) if baseline["failure_rate"] else 0.0,
            "transaction_ids": [t.id for t in members if t.status == "failed"][:200],
        }

    # Group by payment_method.
    by_method: Dict[str, List[Transaction]] = {}
    for t in recent:
        by_method.setdefault(t.payment_method or "unknown", []).append(t)
    for method, members in by_method.items():
        add_group(f"payment_method::{method}", method, members)

    # Group by failure_reason (pinpoint systemic causes like timeouts).
    by_reason: Dict[str, List[Transaction]] = {}
    for t in recent:
        r = t.failure_reason or "unknown"
        by_reason.setdefault(r, []).append(t)
    for reason, members in by_reason.items():
        add_group(f"failure_reason::{reason}", reason, members)

    # Merchant-wide group (always useful).
    add_group("merchant::all", "All Payment Channels", recent)

    # Sort by revenue at risk descending.
    leaks = sorted(groups.values(), key=lambda g: g["revenue_at_risk"], reverse=True)
    return [g for g in leaks if len(g["transaction_ids"]) >= 3]


def _matches(t: Transaction, key: str) -> bool:
    kind, _, value = key.partition("::")
    if kind == "payment_method":
        return (t.payment_method or "unknown") == value
    if kind == "failure_reason":
        return (t.failure_reason or "unknown") == value
    return True


def _zscore(current: Dict[str, float], baseline: Dict[str, float]) -> float:
    """One-sided z-score of current failure rate vs baseline p.

    Uses the normal approximation of the binomial proportion:
        se = sqrt(p_hat * (1 - p_hat) / n)
    with p_hat taken from the pooled baseline.
    """
    base_rate = baseline["failure_rate"]
    n_current = current["count"]
    if n_current == 0:
        return 0.0
    se = np.sqrt((base_rate * (1 - base_rate)) / n_current) if 0 < base_rate < 1 else 0.0
    if se == 0:
        return 0.0
    return float((current["failure_rate"] - base_rate) / se)


def leak_type_for(t: Transaction, all_failures: List[Transaction]) -> str:
    """Map a failed transaction to a leak-type bucket for the explorer."""
    r = (t.failure_reason or "").lower()
    if any(k in r for k in ("timeout", "gateway", "provider", "degraded", "network")):
        return "Payment Degradation"
    if any(k in r for k in ("abandon", "cart")):
        return "Checkout Abandonment"
    if any(k in r for k in ("expired", "subscription", "renewal")):
        return "Subscription Failures"
    if any(k in r for k in ("insufficient", "declined", "limit", "restrict")):
        return "Card & Customer Issues"
    return "Other"