"""API endpoint integration tests.

Uses the real FastAPI app with the `get_db` dependency overridden to feed an
isolated in-memory database, so each test exercises the full route handlers
(including the deterministic modules and agent) without touching the runtime DB.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.core.database import Base, get_db
from app.main import create_app

from conftest import make_case, make_customer, make_transaction

# Default limit used by routes
CASE_COUNT = 5


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    test_db = Session()

    def _override():
        try:
            yield test_db
        finally:
            test_db.close()

    app = create_app()
    app.dependency_overrides[get_db] = _override

    with TestClient(app) as c:
        yield c
        test_db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _seed_basic_data(db):
    cust = make_customer(db)
    db.add(cust)
    db.flush()
    tx = make_transaction(db, customer_id=cust.id, transaction_rev="TXN_1")
    db.add(tx)
    db.flush()
    case = make_case(db, transaction_id=tx.id, case_code="CASE_1001")
    db.add(case)
    db.commit()
    return cust, tx, case


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
    assert body["revenue_at_risk"] >= 0
    assert body["recovery_rate"] >= 0


def test_dashboard_summary_with_case(client):
    _seed_basic_data(client.app.dependency_overrides[get_db].__closure__[0].cell_contents if False else _peek_session(client))
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 200
    assert r.json()["active_cases"] >= 1


def _peek_session(client):
    # The override closure holds the test session; grab it to seed rows.
    from app.core.database import get_db as dep

    override = client.app.dependency_overrides.get(dep)
    # Fall back: seed through a fresh session bound to the same engine is not
    # possible from here, so we require the caller to seed via the client.* approach.
    raise RuntimeError("use client_seeded fixture")


@pytest.fixture()
def client_seeded(client):
    g = client.app.dependency_overrides.get(get_db)
    # Re-open a session against the same in-memory engine (TestClient uses one).
    # Simpler: seed through an endpoint isn't ideal, so we seed with a manual
    # engine mirror. We use the app's own storage path again here.
    return client


def test_leaks_endpoint_empty(client):
    r = client.get("/api/leaks")
    assert r.status_code == 200
    body = r.json()
    assert "detected" in body and "breakdown" in body


def test_cases_list(client):
    r = client.get("/api/cases")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


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