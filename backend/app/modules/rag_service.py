"""RAG / Knowledge Layer — merchant policy retrieval.

Retrieves the most relevant policy documents before the agent proposes an
action, using semantic similarity:

  - PostgreSQL backend: pgvector cosine-distance search.
  - SQLite backend: deterministic in-process hashed bag-of-words embedding
    with cosine similarity. Produces equivalent ranking behaviour so the demo
    works with zero external infrastructure.

Embeddings are deterministic (hashed n-grams) in the fallback, and generated
by a simple feature-hashing model in both backends for consistency. The real
LLM is never involved in *retrieval*.
"""
import hashlib
import json
import logging
import math
import re
import string
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import is_postgres
from app.models import Policy

logger = logging.getLogger("revenova.rag")

VECTOR_DIM = 384


def _tokenize(doc: str) -> List[str]:
    doc = doc.lower()
    doc = re.sub(r"[^\w\s-]", " ", doc)
    return [w for w in doc.split() if w and w not in string.punctuation]


def embed_text(text: str, dim: int = VECTOR_DIM) -> List[float]:
    """Deterministic hashed bag-of-words embedding (with sign hashing).

    Word + 1-gram and 2-gram features are hashed into a fixed dim vector with
    TF scaling. Cosine similarity between these vectors captures topical
    overlap well enough for the policy-retrieval use case. Same function is
    used on both the PostgreSQL (stored in pgvector) and SQLite backends so
    results agree.
    """
    vec = [0.0] * dim
    tokens = _tokenize(text)
    grams: List[str] = []
    grams.extend(tokens)
    grams.extend("".join(tokens[i : i + 2]) for i in range(len(tokens) - 1))

    tf: Dict[str, int] = {}
    for g in grams:
        tf[g] = tf.get(g, 0) + 1
    for g, c in tf.items():
        h = hashlib.blake2b(g.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "big") % dim
        sign = 1.0 if h[4] % 2 == 0 else -1.0
        vec[idx] += sign * (1.0 + math.log(c))
    norm = math.sqrt(sum(v * v for v in vec))
    if norm:
        vec = [v / norm for v in vec]
    return vec


def cosine_sim(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def _encode_for_store(vec: List[float]) -> str:
    return json.dumps(vec)


def _decode_from_store(raw: Any) -> List[float]:
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            loaded = json.loads(raw)
            return [float(x) for x in loaded]
        except Exception:
            return []
    # pgvector returns a numpy-like array
    try:
        return [float(x) for x in raw]
    except Exception:
        return []


def _search_sqlite(db: Session, query_vec: List[float], limit: int = 3) -> List[Policy]:
    policies = db.query(Policy).all()
    scored = []
    for p in policies:
        pv = _decode_from_store(p.embedding)
        sim = cosine_sim(query_vec, pv) if pv else 0.0
        if sim > 0.01:
            scored.append((sim, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:limit]]


def _search_pgvector(db: Session, query_vec: List[float], limit: int = 3) -> List[Policy]:
    """pgvector nearest-neighbour search (PostgreSQL backend)."""
    from pgvector.sqlalchemy import Vector  # noqa: F401
    from sqlalchemy import text as _t
    from sqlalchemy.orm import Session as _S

    vec_literal = str(query_vec)
    sql = _t(
        """
        SELECT id, merchant_id, policy_text
        FROM policies
        ORDER BY embedding <=> CAST(:vec AS vector)
        LIMIT :lim
        """
    )
    rows = db.execute(sql, {"vec": vec_literal, "lim": limit}).fetchall()
    policies = []
    for row in rows:
        p = db.get(Policy, row.id)
        if p:
            policies.append(p)
    return policies


def retrieve_policies(db: Session, query: str, limit: int = 3) -> List[Policy]:
    qv = embed_text(query)
    if is_postgres():
        try:
            return _search_pgvector(db, qv, limit)
        except Exception as exc:  # pragma: no cover
            logger.warning("pgvector search failed (%s); falling back to in-process", exc)
    return _search_sqlite(db, qv, limit)


def store_policy(db: Session, policy_text: str, policy_code: str = "", merchant_id: int = 1) -> Policy:
    pol = db.query(Policy).filter(Policy.policy_code == policy_code).first()
    vec = embed_text(policy_text)
    if pol is None:
        pol = Policy(
            policy_code=policy_code,
            merchant_id=merchant_id,
            policy_text=policy_text,
            embedding=vec if is_postgres() else _encode_for_store(vec),
            semantics=",".join(_tokenize(policy_text)[:40]),
        )
        db.add(pol)
    else:
        pol.policy_text = policy_text
        pol.embedding = vec if is_postgres() else _encode_for_store(vec)
        pol.semantics = ",".join(_tokenize(policy_text)[:40])
    db.commit()
    db.refresh(pol)
    return pol


def seed_policies(db: Session) -> None:
    """Seed the default merchant policies into the knowledge layer."""
    policies = [
        (
            "POL-DISCOUNT",
            "Maximum automatic discount is 10%. Any discount above 10% requires "
            "explicit human approval before it can be offered to a customer. "
            "Discounts are a last resort and should never exceed the recovery "
            "friction cost.",
        ),
        (
            "POL-CONTACT",
            "Never contact a customer more than 3 times within any 7-day window. "
            "Automated recovery messages are limited to one per day. After 3 "
            "contacts with no response, stop automated communication.",
        ),
        (
            "POL-RETRY",
            "Automatic payment retries are limited to 2 per case. A retry may "
            "only be executed when the underlying failure cause has likely "
            "resolved (e.g. delayed retry after channel degradation).",
        ),
        (
            "POL-ESCALATION",
            "High-value customers (lifetime value above ₹2,00,000) may always be "
            "escalated to human support. Transactions above ₹1,00,000 always "
            "require human approval before any automated recovery action.",
        ),
        (
            "POL-PAYMENT-LINK",
            "Secure payment links may be sent for amounts at or below ₹1,00,000 "
            "without human approval. Payment links should always reference a "
            "valid, unique transaction and expire within 30 days.",
        ),
        (
            "POL-OFFER",
            "Offering an alternative payment method is encouraged when a decline "
            "is customer-specific (expired card, insufficient funds, card not "
            "present). Never auto-execute a retry against an expired card; the "
            "customer must first update their payment method.",
        ),
    ]
    for code, pt in policies:
        store_policy(db, pt, code)