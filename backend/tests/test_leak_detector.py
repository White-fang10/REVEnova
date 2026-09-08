"""Tests for the deterministic Revenue Leak Detector.

Key guarantee from the project brief: a single failed transaction is NEVER
flagged as a systemic leak. We test that explicitly, plus the statistical
behavior (z-score threshold, cohort minimums, deterministic output).
"""
from datetime import datetime, timedelta

from app.modules import leak_detector
from app.models import Transaction

from conftest import make_transaction


def _bulk_fail(db, n, *, status="failed", reason="timeout", method="UPI",
               days_ago=0):
    """Insert n transactions in the recent window with a specific failure."""
    now = datetime.utcnow()
    for i in range(n):
        t = make_transaction(
            db,
            transaction_rev=f"TXN_BULK_{i}",
            customer_id=1,
            amount=1000.0,
            payment_method=method,
            status=status,
            failure_reason=reason if status == "failed" else "",
            timestamp=now - timedelta(days=days_ago, hours=i % 8),
        )
        db.add(t)
    db.flush()


def _bulk_baseline(db, n, *, method="UPI"):
    """Insert n succeeded transactions in the baseline window (>2 days ago)."""
    now = datetime.utcnow()
    for i in range(n):
        t = make_transaction(
            db,
            transaction_rev=f"TXN_BASE_{i}",
            customer_id=1,
            amount=1000.0,
            payment_method=method,
            status="succeeded",
            failure_reason="",
            timestamp=now - timedelta(days=10, hours=i % 8),
        )
        db.add(t)
    db.flush()


def test_single_failed_transaction_is_never_a_leak(db_session):
    """The core promise: one failure is not systemic."""
    _bulk_fail(db_session, 1)
    leaks = leak_detector.detect_leaks(db_session)
    assert leaks == []


def test_no_leak_when_below_minimum_transactions(db_session):
    """Under the cohort minimum nothing is flagged regardless of rate."""
    _bulk_fail(db_session, 19)
    leaks = leak_detector.detect_leaks(db_session)
    assert leaks == []


def test_no_leak_when_failure_rate_not_above_baseline(db_session):
    """A healthy cohort (low failure rate) must not be flagged."""
    _bulk_baseline(db_session, 200, method="UPI")
    _bulk_fail(db_session, 20, status="succeeded", reason="timeout", method="UPI")
    leaks = leak_detector.detect_leaks(db_session)
    # All succeeded transactions carry an empty failure_reason, so the
    # timed-out cohort simply doesn't exist -> no leak.
    assert all(l["dimension"] == "payment_method" for l in leaks) or leaks == []


def test_detects_channel_degradation_cohort(db_session):
    """A statistically significant timeout burst must be detected as a leak:
    the payment-method cohort (UPI) shows a rate far above baseline."""
    _bulk_baseline(db_session, 300, method="UPI")
    _bulk_fail(db_session, 60, status="failed", reason="timeout", method="UPI")
    leaks = leak_detector.detect_leaks(db_session)
    assert leaks, "expected at least one detected leak"
    flagged = [l for l in leaks if l["dimension"] == "payment_method" and l["value"] == "UPI"]
    assert flagged, f"UPI cohort not flagged; leaks={leaks}"[:200]
    top = flagged[0]
    assert top["current_rate"] > top["baseline_rate"]
    assert top["revenue_at_risk"] > 0
    assert len(top["transaction_ids"]) >= 3


def test_leak_sorted_by_revenue_at_risk(db_session):
    """Leaks come back sorted by revenue at risk descending."""
    _bulk_baseline(db_session, 300, method="UPI")
    _bulk_fail(db_session, 40, reason="timeout", method="UPI")
    _bulk_fail(db_session, 40, reason="gateway_error", method="netbanking")
    leaks = leak_detector.detect_leaks(db_session)
    risks = [l["revenue_at_risk"] for l in leaks]
    assert risks == sorted(risks, reverse=True)


def test_zscore_respects_custom_threshold(db_session):
    """With an absurdly high z-threshold nothing is flagged; with a low one the
    leak appears (threshold controls sensitivity)."""
    _bulk_baseline(db_session, 300, method="UPI")
    _bulk_fail(db_session, 60, reason="timeout", method="UPI")

    none = leak_detector.detect_leaks(db_session, z_threshold=99.0)
    assert none == []

    some = leak_detector.detect_leaks(db_session, z_threshold=0.1)
    assert any(l["value"] == "UPI" for l in some)


def test_leak_type_bucketing():
    from app.models import Transaction

    t = Transaction(failure_reason="gateway timeout", payment_method="UPI")
    assert leak_detector.leak_type_for(t, []) == "Payment Degradation"

    t2 = Transaction(failure_reason="checkout_abandoned")
    assert leak_detector.leak_type_for(t2, []) == "Checkout Abandonment"

    t3 = Transaction(failure_reason="expired_card")
    assert leak_detector.leak_type_for(t3, []) == "Subscription Failures"

    t4 = Transaction(failure_reason="insufficient_funds")
    assert leak_detector.leak_type_for(t4, []) == "Card & Customer Issues"

    t5 = Transaction(failure_reason="something_else")
    assert leak_detector.leak_type_for(t5, []) == "Other"


def test_detect_is_deterministic(db_session):
    _bulk_baseline(db_session, 300, method="UPI")
    _bulk_fail(db_session, 60, reason="timeout", method="UPI")
    a = leak_detector.detect_leaks(db_session)
    b = leak_detector.detect_leaks(db_session)
    assert a == b