"""API endpoint integration tests.

Uses the real FastAPI app with the `get_db` dependency overridden to feed an
isolated in-memory database, so each test exercises the full route handlers
(including the deterministic modules and agent) without touching the runtime DB.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import create_app

from tests.conftest import make_case, make_customer, make_transaction


@pytest.fixture()
def _env():
    """Holds the isolated in-memory engine/session used by the TestClient."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    class Env:
        def __init__(self):
            self.session = Session()
            self.engine = engine

        def commit(self):
            self.session.commit()

    env = Env()
    yield env
    env.session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def client(_env):
    def _override():
        try:
            yield _env.session
        finally:
            pass

    app = create_app()
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def client_with_case(_env):
    """A client with one seeded customer + failed tx + open case."""
    cust = make_customer(_env.session)
    _env.session.add(cust)
    _env.session.flush()
    tx = make_transaction(_env.session, customer_id=cust.id, transaction_rev="TXN_1")
    _env.session.add(tx)
    _env.session.flush()
    case = make_case(_env.session, transaction_id=tx.id, case_code="CASE_1001")
    _env.session.add(case)
    _env.commit()

    def _override():
        try:
            yield _env.session
        finally:
            pass

    app = create_app()
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c, case.id, tx.id


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "app" in body


def test_dashboard_summary_empty_db(client):
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["currency"] == "INR"
    assert body["revenue_at_risk"] == 0
    assert body["recovery_rate"] == 0
    assert body["active_cases"] == 0


def test_dashboard_summary_with_case(client_with_case):
    client, case_id, _ = client_with_case
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["active_cases"] >= 1
    assert body["revenue_at_risk"] > 0


def test_leaks_endpoint_empty(client):
    r = client.get("/api/leaks")
    assert r.status_code == 200
    body = r.json()
    assert "detected" in body and "breakdown" in body


def test_cases_list(client_with_case):
    client, case_id, _ = client_with_case
    r = client.get("/api/cases")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    assert any(row["id"] == case_id for row in rows)


def test_case_detail(client_with_case):
    client, case_id, _ = client_with_case
    r = client.get(f"/api/cases/{case_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["case_code"] == "CASE_1001"
    assert "trace" in body


def test_run_case_no_execute(client_with_case):
    client, case_id, _ = client_with_case
    r = client.post(f"/api/cases/{case_id}/run?execute=false")
    assert r.status_code == 200
    body = r.json()
    assert body["best"] is not None
    assert len(body["strategies"]) >= 3
    assert len(body["trace"]) > 0


def test_approve_case(client_with_case):
    client, case_id, _ = client_with_case
    r = client.post(f"/api/cases/{case_id}/approve")
    assert r.status_code == 200
    assert r.json()["approved"] is True


def test_escalate_case(client_with_case):
    client, case_id, _ = client_with_case
    r = client.post(f"/api/cases/{case_id}/escalate")
    assert r.status_code == 200
    body = r.json()
    assert body["escalated"] is True
    assert body["case"]["status"] == "escalated"


def test_case_strategies(client_with_case):
    client, case_id, _ = client_with_case
    r = client.post(f"/api/cases/{case_id}/run?execute=false")  # generates strategies
    assert r.status_code == 200
    r2 = client.get(f"/api/cases/{case_id}/strategies")
    assert r2.status_code == 200
    body = r2.json()
    assert body["equation"]["formula"].startswith("Expected Value")
    assert len(body["strategies"]) >= 3
    assert "best" in body


def test_audit_endpoint(client_with_case):
    client, case_id, _ = client_with_case
    client.post(f"/api/cases/{case_id}/run?execute=false")
    r = client.get("/api/audit")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    assert len(rows) >= 1


def test_ingest_failed_creates_case(client):
    payload = {
        "transaction_id": "TXN_ING_1",
        "customer_id": "CUS_X",
        "amount": 2500.0,
        "payment_method": "card",
        "device": "Web",
        "status": "failed",
        "failure_reason": "expired_card",
    }
    r = client.post("/api/ingest", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["ingested"] is True
    assert body["recovery_case_id"] is not None


def test_ingest_succeeded_no_case(client):
    payload = {
        "transaction_id": "TXN_ING_OK",
        "customer_id": "CUS_Y",
        "amount": 1200.0,
        "payment_method": "card",
        "device": "Web",
        "status": "succeeded",
    }
    r = client.post("/api/ingest", json=payload)
    assert r.status_code == 200
    assert r.json()["recovery_case_id"] is None


def test_case_not_found_404(client):
    r = client.get("/api/cases/999999")
    assert r.status_code == 404


def test_demo_not_ready_without_seed(client):
    r = client.get("/api/demo")
    assert r.status_code == 200
    assert r.json()["ready"] is False


def test_learning_endpoint(client):
    r = client.get("/api/learning")
    assert r.status_code == 200
    body = r.json()
    assert "learned" in body
    assert "positioning_note" in body
    assert "automatically" not in body["positioning_note"].lower()


def test_strategies_endpoint_case_not_found(client):
    r = client.get("/api/cases/424242/strategies")
    assert r.status_code == 404


def test_schedule_followup(client_with_case):
    client, case_id, _ = client_with_case
    r = client.post(f"/api/cases/{case_id}/schedule-followup?in_days=2")
    assert r.status_code == 200
    assert r.json()["scheduled"] is True


def test_scan_leaks_endpoint(client):
    r = client.post("/api/maintenance/scan-leaks")
    assert r.status_code == 200
    assert "status" in r.json() or "dispatched" in r.json()