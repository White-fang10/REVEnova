"""Shared pytest fixtures.

Creates an isolated in-memory SQLite database per test so no test pollutes the
runtime database (data/revenova.db). The app's ORM models are re-used verbatim.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401  ensure all models registered on Base
from app.core.database import Base


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def seed_policies(db_session):
    from app.modules import rag_service

    rag_service.seed_policies(db_session)
    return db_session.query(models.Policy).all()


def make_customer(db, **kw):
    defaults = dict(
        customer_ref="CUS_9999",
        merchant_id=1,
        name="Test Customer",
        segment="standard",
        lifetime_value=60_000.0,
        payment_method="card",
    )
    defaults.update(kw)
    return models.Customer(**defaults)


def make_transaction(db, **kw):
    defaults = dict(
        transaction_rev="TXN_TEST",
        amount=8400.0,
        payment_method="card",
        device="Web",
        status="failed",
        failure_reason="expired_card",
        timestamp=datetime.utcnow(),
    )
    defaults.update(kw)
    return models.Transaction(**defaults)


def make_case(db, **kw):
    defaults = dict(
        case_code="CASE_TEST",
        risk_score=0.7,
        recovery_probability=0.6,
        root_cause="Expired card on file",
        confidence=0.9,
        leak_type="Subscription Failures",
        status="open",
        revenue_at_risk=8400.0,
        contact_count=0,
        consecutive_failures=0,
    )
    defaults.update(kw)
    return models.RecoveryCase(**defaults)


@pytest.fixture()
def demo_data(db_session):
    """A customer + failed expired-card transaction + open case (like the README
    demo scenario, in isolation)."""
    cust = make_customer(db_session, segment="high_value", lifetime_value=850_000.0)
    db_session.add(cust)
    db_session.flush()
    tx = make_transaction(db_session, customer_id=cust.id, transaction_rev="TXN_48291")
    db_session.add(tx)
    db_session.flush()
    case = make_case(db_session, case_code="CASE_48291", transaction_id=tx.id, revenue_at_risk=8400.0)
    db_session.add(case)
    db_session.flush()
    return {"customer": cust, "transaction": tx, "case": case}