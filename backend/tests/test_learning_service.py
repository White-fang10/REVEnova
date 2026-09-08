"""Tests for the Learning Loop service.

Verifies that learned recovery rates are computed ONLY from recorded
recovery_outcomes, that the in-memory context is refreshed by load(), and that
record() only mutates the cache (never the DB directly).
"""
from app.models import (
    RecoveryAction,
    RecoveryCase,
    RecoveryOutcome,
    RecoveryStrategy,
)
from app.services.learning_service import LearningService

from tests.conftest import make_case


_case_seq = [0]


def _seed_history(db, *, strategy_key="alternative_payment", attempts=3, successes=2):
    _case_seq[0] += 1
    case = make_case(db, case_code=f"CASE_LRN_{_case_seq[0]}")
    db.add(case)
    db.flush()
    strat = RecoveryStrategy(
        case_id=case.id,
        strategy=strategy_key,
        predicted_recovery=0.5,
        cost=2.0,
        friction_score=1.0,
        expected_value=100.0,
        recommended=True,
    )
    db.add(strat)
    db.flush()
    for i in range(attempts):
        act = RecoveryAction(
            case_id=case.id,
            strategy_id=strat.id,
            action="send_payment_link",
            tool="agent_send_payment_link",
            status="succeeded" if i < successes else "failed",
            predicted_recovery=0.5,
            policy_checked="R04",
            policy_result="allowed",
            detail=f"attempt {i}",
        )
        db.add(act)
        db.flush()
        db.add(RecoveryOutcome(
            action_id=act.id,
            case_id=case.id,
            predicted_recovery=0.5,
            amount_recovered=5000.0 if i < successes else 0.0,
            success=i < successes,
            recovery_time=60 if i < successes else 0,
        ))
    db.flush()


def test_snapshot_computes_rate_from_outcomes(db_session):
    _seed_history(db_session, strategy_key="alternative_payment", attempts=3, successes=2)
    svc = LearningService()
    snap = svc.snapshot(db_session)
    row = next(r for r in snap if r["strategy"] == "alternative_payment")
    assert row["attempts"] == 3
    assert row["successes"] == 2
    assert abs(row["recovery_rate"] - 2 / 3) < 0.001  # rounded to 3 dp
    assert abs(row["amount_recovered"] - 10000.0) < 1e-6


def test_snapshot_empty_db_yields_empty(db_session):
    svc = LearningService()
    assert svc.snapshot(db_session) == []


def test_load_populates_context(db_session):
    _seed_history(db_session, strategy_key="delayed_retry", attempts=2, successes=1)
    svc = LearningService()
    svc.load(db_session)
    ctx = svc.context()
    assert ctx["delayed_retry"] == 0.5
    assert "immediate_retry" not in ctx  # nothing recorded for that slot


def test_load_ignores_unrecorded_actions(db_session):
    """An action with NO outcome row must not contribute to learned rates."""
    case = make_case(db_session)
    db_session.add(case)
    db_session.flush()
    strat = RecoveryStrategy(case_id=case.id, strategy="immediate_retry")
    db_session.add(strat)
    db_session.flush()
    db_session.add(RecoveryAction(
        case_id=case.id, strategy_id=strat.id, action="execute_retry",
        status="executed", predicted_recovery=0.31,
    ))
    db_session.flush()
    svc = LearningService()
    assert svc.snapshot(db_session) == []


def test_record_tracks_rate(db_session):
    svc = LearningService()
    svc.record("alternative_payment", success=True)
    svc.record("alternative_payment", success=False)
    svc.record("alternative_payment", success=True)
    assert svc.context()["alternative_payment"] == 2 / 3


def test_record_mutates_cache_only(db_session):
    svc = LearningService()
    before_rows = db_session.query(RecoveryOutcome).count()
    svc.record("payment_method_update", success=True)
    assert db_session.query(RecoveryOutcome).count() == before_rows  # no DB writes
    assert svc.context()["payment_method_update"] > 0


def test_learning_from_multiple_strategies(db_session):
    _seed_history(db_session, strategy_key="alternative_payment", attempts=3, successes=1)
    _seed_history(db_session, strategy_key="delayed_retry", attempts=2, successes=2)
    svc = LearningService()
    snap = svc.snapshot(db_session)
    by_key = {r["strategy"]: r for r in snap}
    assert abs(by_key["alternative_payment"]["recovery_rate"] - 1 / 3) < 0.001
    assert abs(by_key["delayed_retry"]["recovery_rate"] - 1.0) < 0.001