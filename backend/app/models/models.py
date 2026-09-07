"""SQLAlchemy ORM models for all REVEnova tables.

Schema (implemented as-is from the project definition) with one pragmatic
deviation: the ``policies.embedding`` column is either a real pgvector Vector
(when running on PostgreSQL) or a serialized JSON byte-blob (SQLite fallback).
"""
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base, is_postgres

# ---------------------------------------------------------------------------
# Cross-backend embedding column.
#
# On PostgreSQL we use the native pgvector type so we can do real
# cosine-distance RAG searches. On SQLite we store a JSON-encoded vector in a
# Text column and do the search in-process. Both are wrapped behind the same
# "embedding" attribute below.
# ---------------------------------------------------------------------------
if is_postgres():
    try:
        from pgvector.sqlalchemy import Vector

        EMBEDDING_TYPE = Vector(384)
    except Exception:  # pragma: no cover
        EMBEDDING_TYPE = Text()
else:
    EMBEDDING_TYPE = Text()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    merchant_id = Column(Integer, index=True)
    role = Column(String(50), default="admin")
    name = Column(String(120), default="")
    email = Column(String(120), default="")
    created_at = Column(DateTime, server_default=func.now())


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True)
    customer_ref = Column(String(40), unique=True, index=True, default="")
    merchant_id = Column(Integer, index=True)
    name = Column(String(120), default="")
    panel_email = Column(String(120), default="")
    panel_phone = Column(String(40), default="")
    segment = Column(String(40), default="standard")  # high_value | standard | churn_risk
    lifetime_value = Column(Float, default=0.0)
    payment_method = Column(String(40), default="card")
    created_at = Column(DateTime, server_default=func.now())


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    transaction_rev = Column(String(40), unique=True, index=True, default="")
    customer_id = Column(Integer, ForeignKey("customers.id"), index=True)
    amount = Column(Float, default=0.0)
    payment_method = Column(String(40), default="card")
    device = Column(String(40), default="")
    status = Column(String(20), default="failed")  # succeeded | failed | pending | refunded
    failure_reason = Column(String(80), default="")
    timestamp = Column(DateTime, index=True, default=datetime.utcnow)

    customer = relationship("Customer", backref="transactions")


class RecoveryCase(Base):
    __tablename__ = "recovery_cases"

    id = Column(Integer, primary_key=True)
    case_code = Column(String(40), unique=True, index=True, default="")
    transaction_id = Column(Integer, ForeignKey("transactions.id"), index=True)
    risk_score = Column(Float, default=0.0)
    recovery_probability = Column(Float, default=0.0)
    root_cause = Column(String(120), default="")
    confidence = Column(Float, default=0.0)
    leak_type = Column(String(60), default="")
    status = Column(String(30), default="open")  # open | approved | escalated | recovered | closed | stopped
    revenue_at_risk = Column(Float, default=0.0)
    contact_count = Column(Integer, default=0)
    consecutive_failures = Column(Integer, default=0)
    created_at = Column(DateTime, index=True, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    transaction = relationship("Transaction", backref="recovery_cases")
    strategies = relationship("RecoveryStrategy", back_populates="case", cascade="all, delete-orphan")
    actions = relationship("RecoveryAction", back_populates="case", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="case", cascade="all, delete-orphan")


class RecoveryStrategy(Base):
    __tablename__ = "recovery_strategies"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("recovery_cases.id"), index=True)
    strategy = Column(String(60), default="")          # immediate_retry | delayed_retry | ...
    predicted_recovery = Column(Float, default=0.0)     # 0..1
    cost = Column(Float, default=0.0)                   # intervention cost in ₹
    friction_score = Column(Float, default=0.0)         # customer friction cost in ₹
    expected_value = Column(Float, default=0.0)
    is_AI_proposed = Column(Boolean, default=False)
    recommended = Column(Boolean, default=False)

    case = relationship("RecoveryCase", back_populates="strategies")
    actions = relationship("RecoveryAction", back_populates="strategy")


class RecoveryAction(Base):
    __tablename__ = "recovery_actions"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("recovery_cases.id"), index=True)
    strategy_id = Column(Integer, ForeignKey("recovery_strategies.id"), nullable=True)
    action = Column(String(60), default="")             # execute_retry | send_payment_link | ...
    tool = Column(String(60), default="")
    status = Column(String(30), default="executed")     # executed | failed | blocked | escalated | succeeded
    predicted_recovery = Column(Float, default=0.0)
    policy_checked = Column(String(120), default="")
    policy_result = Column(String(30), default="allowed")  # allowed | blocked | approval_required
    detail = Column(Text, default="")
    timestamp = Column(DateTime, index=True, default=datetime.utcnow)

    case = relationship("RecoveryCase", back_populates="actions")
    strategy = relationship("RecoveryStrategy", back_populates="actions")
    outcome = relationship("RecoveryOutcome", back_populates="action", uselist=False, cascade="all, delete-orphan")


class RecoveryOutcome(Base):
    __tablename__ = "recovery_outcomes"

    id = Column(Integer, primary_key=True)
    action_id = Column(Integer, ForeignKey("recovery_actions.id"), index=True)
    case_id = Column(Integer, index=True, default=0)
    predicted_recovery = Column(Float, default=0.0)
    amount_recovered = Column(Float, default=0.0)
    success = Column(Boolean, default=False)
    recovery_time = Column(Integer, default=0)  # minutes
    recorded_at = Column(DateTime, default=datetime.utcnow)

    action = relationship("RecoveryAction", back_populates="outcome")


class Policy(Base):
    __tablename__ = "policies"

    id = Column(Integer, primary_key=True)
    policy_code = Column(String(40), unique=True, index=True, default="")
    merchant_id = Column(Integer, index=True, default=1)
    policy_text = Column(Text, default="")
    embedding = Column(EMBEDDING_TYPE, nullable=True)
    semantics = Column(Text, default="")   # keywords / semantic tags for SQLite fallback search


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("recovery_cases.id"), index=True, nullable=True)
    agent = Column(String(60), default="")       # e.g. "leak_detector", "diagnosis", "ai_agent"
    decision = Column(String(60), default="")    # e.g. "detected_leak", "selected_strategy"
    reason = Column(Text, default="")
    policy_checked = Column(String(120), default="")
    action = Column(String(60), default="")
    detail = Column(Text, default="")
    amount = Column(Float, default=0.0)
    timestamp = Column(DateTime, index=True, default=datetime.utcnow)

    case = relationship("RecoveryCase", back_populates="audit_logs")
