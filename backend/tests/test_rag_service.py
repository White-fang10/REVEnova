"""Tests for the RAG / knowledge layer (policy retrieval).

Verifies determinism of embeddings, cosine similarity behaviour, and that the
retrieval layer returns relevant merchant policies for a query (same behaviour
on SQLite fallback and, structurally, on pgvector).
"""
from app.modules import rag_service
from app.modules.rag_service import cosine_sim, embed_text
from app.models import Policy


def test_embed_deterministic():
    v1 = embed_text("maximum automatic discount is 10 percent")
    v2 = embed_text("maximum automatic discount is 10 percent")
    assert v1 == v2
    assert len(v1) == rag_service.VECTOR_DIM


def test_embed_normalized_vectors():
    v = embed_text("retry limit two attempts per case")
    norm = sum(x * x for x in v) ** 0.5
    assert abs(norm - 1.0) < 1e-6


def test_embeddings_differ_between_topics():
    a = embed_text("discount approval threshold")
    b = embed_text("automatic payment retries are limited")
    same = embed_text("discount approval threshold and guidance")
    assert cosine_sim(a, same) > cosine_sim(a, b)


def test_retrieve_policies_returns_relevant(seed_policies, db_session):
    res = rag_service.retrieve_policies(db_session, "how many times may we retry a failed payment", limit=3)
    codes = [p.policy_code for p in res]
    assert "POL-RETRY" in codes, f"expected POL-RETRY in results, got {codes}"


def test_retrieve_discount_policy(seed_policies, db_session):
    res = rag_service.retrieve_policies(db_session, "can we offer a 20 percent discount without approval", limit=2)
    codes = [p.policy_code for p in res]
    assert "POL-DISCOUNT" in codes, f"expected POL-DISCOUNT in results, got {codes}"


def test_store_and_roundtrip_policy(db_session):
    pol = rag_service.store_policy(
        db_session,
        "Suspicious payment patterns must be reviewed by a human before retry.",
        policy_code="POL-TEST",
    )
    assert pol.id is not None
    assert pol.policy_text.startswith("Suspicious")
    stored = db_session.get(Policy, pol.id)
    assert stored is not None
    assert stored.policy_text.startswith("Suspicious")
    found = rag_service.retrieve_policies(db_session, "suspicious payment requires human review", limit=5)
    assert any(p.policy_code == "POL-TEST" for p in found)


def test_store_policy_is_idempotent(db_session):
    rag_service.store_policy(db_session, "policy text one", policy_code="POL-REP")
    rag_service.store_policy(db_session, "policy text two", policy_code="POL-REP")
    rows = db_session.query(Policy).filter(Policy.policy_code == "POL-REP").all()
    assert len(rows) == 1


def test_embedding_stored_on_policy(db_session):
    rag_service.store_policy(db_session, "payment links expire within thirty days", policy_code="POL-STORE-EMB")
    row = db_session.query(Policy).filter(Policy.policy_code == "POL-STORE-EMB").first()
    assert row.embedding is not None and len(row.embedding) > 10