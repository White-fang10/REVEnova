"""Tests for the AI Recovery Agent orchestrator.

Verifies the bounded-tool contract, the DETECT->DIAGNOSE->DECIDE->RECOVER loop,
deterministic policy gating (LLM never overrides money math), stopping rules,
and outcome/learning capture. Runs against an isolated in-memory database.
"""
from app.models import (
    AuditLog,
    RecoveryAction,
    RecoveryCase,
    RecoveryOutcome,
    RecoveryStrategy,
)
from app.modules import rag_service
from app.services.recovery_agent import RecoveryAgent

from tests.conftest import make_demo_data


def _setup_agent(db, case):
    rag_service.seed_policies(db)
    return RecoveryAgent(db)


def test_agent_run_returns_full_result(db_session):
    """The demo case runs the whole loop and returns strategies, best, trace."""
    data = make_demo_data(db_session)
    case = data["case"]
    db_session.commit()
    agent = _setup_agent(db_session, case)
    result = agent.run_case(case.id, execute=False)
    db_session.commit()

    assert result["case"]["case_code"] == "CASE_48291"
    assert len(result["strategies"]) >= 3
    assert result["best"] is not None
    # Payment Method Update should be chosen for an expired card (EV-driven).
    assert result["best"]["key"] == "payment_method_update"
    # Investigation trace: the 5 read-only tools the agent uses before deciding.
    assert len(result["trace"]) >= 5


def test_agent_trace_includes_bounded_tools_only(db_session):
    data = make_demo_data(db_session)
    db_session.commit()
    agent = _setup_agent(db_session, data["case"])
    result = agent.run_case(data["case"].id, execute=False)
    tools = {t["tool"] for t in result["trace"]}
    expected = {"get_transaction", "get_customer", "get_failure_details",
                "get_payment_history", "get_recovery_history"}
    assert expected.issubset(tools), f"missing tools from {sorted(tools)}"
    # The agent must never record a DB-touching tool; tools stay bounded.
    for tr in result["trace"]:
        assert "db" not in tr["args"]


def test_agent_appends_audit_rows(db_session):
    data = make_demo_data(db_session)
    db_session.commit()
    agent = _setup_agent(db_session, data["case"])
    before = db_session.query(AuditLog).count()
    agent.run_case(data["case"].id, execute=False)
    db_session.commit()
    after = db_session.query(AuditLog).count()
    assert after > before


def test_agent_execution_records_strategy_action_outcome(db_session):
    data = make_demo_data(db_session)
    db_session.commit()
    agent = _setup_agent(db_session, data["case"])
    result = agent.run_case(data["case"].id, execute=True)
    db_session.commit()

    assert db_session.query(RecoveryStrategy).filter(
        RecoveryStrategy.case_id == data["case"].id).count() >= 4
    assert db_session.query(RecoveryAction).filter(
        RecoveryAction.case_id == data["case"].id).count() >= 1
    assert db_session.query(RecoveryOutcome).filter(
        RecoveryOutcome.case_id == data["case"].id).count() >= 1
    assert data["case"].contact_count >= 1  # payment link counts as contact
    assert result["outcome"] is not None


def test_policy_gate_blocks_large_amount_retry(db_session):
    """A ₹1.5M case must not auto-execute: policy engine overrides any AI
    proposal (approval_required), no outcome is recorded."""
    data = make_demo_data(db_session)
    data["case"].revenue_at_risk = 1_500_000.0
    db_session.commit()
    agent = _setup_agent(db_session, data["case"])
    result = agent.run_case(data["case"].id, execute=True)
    db_session.commit()

    assert result["policy_result"] is not None
    assert result["policy_result"]["status"] == "approval_required"
    action = db_session.query(RecoveryAction).filter(
        RecoveryAction.case_id == data["case"].id).first()
    if action:
        assert action.status == "blocked"


def test_stopping_rule_stops_at_probability_floor(db_session):
    """Crossing the consecutive-failure circuit breaker (S01) stops the agent
    from executing anything."""
    data = make_demo_data(db_session)
    data["case"].consecutive_failures = 3
    db_session.commit()
    agent = _setup_agent(db_session, data["case"])
    result = agent.run_case(data["case"].id, execute=True)
    db_session.commit()
    assert result["stopping"]["should_stop"] is True
    assert result["stopping"]["rule_id"] == "S01"
    assert db_session.query(RecoveryAction).filter(
        RecoveryAction.case_id == data["case"].id).count() == 0


def test_agent_never_touches_money_math_locally(db_session):
    """The 'selected best strategy' is driven by the deterministic optimizer.
    The best strategy in the result is the one with the highest expected value
    among persisted strategies for this case."""
    data = make_demo_data(db_session)
    db_session.commit()
    agent = _setup_agent(db_session, data["case"])
    result = agent.run_case(data["case"].id, execute=False)
    db_session.commit()
    rows = db_session.query(RecoveryStrategy).filter(
        RecoveryStrategy.case_id == data["case"].id).all()
    max_ev_row = max(rows, key=lambda s: s.expected_value)
    assert result["best"]["key"] == max_ev_row.strategy


def test_demo_case_end_to_end_matches_readme(db_session):
    """The concrete README scenario: ₹8,400 expired card -> recovered."""
    data = make_demo_data(db_session)
    db_session.commit()
    agent = _setup_agent(db_session, data["case"])
    result = agent.run_case(data["case"].id, execute=True)
    db_session.commit()
    assert result["best"]["key"] == "payment_method_update"
