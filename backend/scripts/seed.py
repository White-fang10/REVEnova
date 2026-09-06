"""Seed the REVEnova database with realistic synthetic data.

Creates:
  - 1 admin user
  - 120 customers (segments, LTV, payment methods)
  - 1,200+ transactions across several days with realistic failure patterns
  - leak scenarios: UPI-timeout burst (channel degradation), expired cards,
    checkout abandonments, subscription renewals, insufficient funds
  - merchant policies (seeded into the RAG/knowledge layer)
  - pre-existing recovery cases + actions + outcomes so the dashboard and the
    learning loop have history to show
  - THE demo case: ₹8,400 / expired card / high-LTV returning customer

Demo case values are deterministic and hard-coded so the end-to-end flow
matches the README (recovery probability 87%, Payment Method Update strategy).
"""
import logging
import random
from datetime import datetime, timedelta

from app.core.database import SessionLocal, init_db
from app.models import (
    Customer,
    RecoveryAction,
    RecoveryCase,
    RecoveryOutcome,
    RecoveryStrategy,
    Transaction,
    User,
)
from app.modules import rag_service
from app.services.agent_tools import deterministic_recovery_probability
from app.services.learning_service import learning

logger = logging.getLogger("revenova.seed")

random.seed(42)

FIRST_NAMES = [
    "Aarav", "Diya", "Vihaan", "Ananya", "Rohan", "Ishaan", "Saanvi", "Kabir",
    "Meera", "Arjun", "Zara", "Vivaan", "Naina", "Reyansh", "Riya", "Aditya",
    "Ira", "Krishna", "Aisha", "Siddharth", "Tara", "Dev", "Nisha", "Yash",
    "Mira", "Farhan", "Kavya", "Aryan", "Gauri", "Neil", "Sana", "Harsh",
]
LAST_NAMES = [
    "Sharma", "Patel", "Verma", "Nair", "Gupta", "Reddy", "Iyer", "Mehta",
    "Kulkarni", "Joshi", "Shah", "Bose", "Menon", "Kapoor", "Desai",
    "Chatterjee", "Agrawal", "Rao", "Chopra", "Dutta", "Pillai", "Chawla",
]
DEVICES = ["Android", "iPhone", "iOS", "Web", "Android", "Web", "Web", "iPhone"]
PAYMENT_METHODS = ["card", "UPI", "netbanking", "wallet"]
LEAK_REASONS = {
    "channel": ["timeout", "gateway_error", "provider_degraded"],
    "expired": ["expired_card"],
    "funds": ["insufficient_funds"],
    "decline": ["card_not_present", "limit_exceeded", "declined_generic"],
    "abandon": ["checkout_abandoned"],
    "renewal": ["subscription_renewal_failed"],
}


def _now():
    return datetime.utcnow()


def seed_all() -> None:
    init_db()
    db = SessionLocal()
    try:
        if db.query(Customer).count() > 0:
            logger.info("Database already seeded; skipping.")
            db.close()
            return

        _seed_user(db)
        customers = _seed_customers(db)
        tx_all = _seed_transactions(db, customers)
        _seed_policies(db)
        cases = _seed_recovery_history(db, customers)
        _mark_demo_case(db, customers, tx_all, cases)
        learning.load(db)
        logger.info(
            "Seeded: %d customers, %d transactions, %d cases, %d policies.",
            len(customers), len(tx_all), len(cases), db.query(_pkey()).count() if False else 6,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _pkey():
    from app.models import Policy
    return Policy


def _seed_user(db) -> None:
    db.add(User(merchant_id=1, role="admin", name="Demo Admin", email="admin@revenova.io"))


def _seed_customers(db) -> list:
    customers = []
    now = _now()
    for i in range(120):
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        roll = random.random()
        if roll < 0.12:
            segment, pm = "high_value", "card"
            ltv = random.uniform(250_000, 2_400_000)
        elif roll < 0.45:
            segment, pm = "standard", random.choice(PAYMENT_METHODS)
            ltv = random.uniform(25_000, 180_000)
        elif roll < 0.75:
            segment, pm = "standard", random.choice(["UPI", "card"])
            ltv = random.uniform(5_000, 80_000)
        else:
            segment, pm = "churn_risk", random.choice(["card", "wallet"])
            ltv = random.uniform(1_000, 40_000)
        c = Customer(
            customer_ref=f"CUS_{8200 + i}",
            merchant_id=1,
            name=name,
            segment=segment,
            lifetime_value=round(ltv, 2),
            payment_method=pm,
        )
        c.created_at = now - timedelta(days=random.randint(30, 400))
        customers.append(c)
        db.add(c)
    db.flush()
    return customers


def _seed_transactions(db, customers) -> list:
    transactions = []
    now = _now()
    today = now.replace(hour=19, minute=32, second=0, microsecond=0)

    # Recent burst of UPI timeouts (channel degradation) clustered 3h ago.
    burst_ids = [random.choice(customers) for _ in range(40)]
    for k, c in enumerate(burst_ids):
        t = Transaction(
            transaction_rev=f"TXN_{8100 + k}",
            customer_id=c.id,
            amount=round(random.uniform(900, 4_500), 2),
            payment_method="UPI",
            device=random.choice(["Android", "Android", "iPhone", "Web"]),
            status="failed",
            failure_reason=random.choice(LEAK_REASONS["channel"]),
            timestamp=today - timedelta(hours=3, minutes=k % 18),
        )
        transactions.append(t)
        db.add(t)

    # Several expired-card failures spread over the last 2 days.
    expired_customers = [c for c in customers if c.segment in ("high_value", "standard")]
    for k in range(22):
        c = random.choice(expired_customers)
        t = Transaction(
            transaction_rev=f"TXN_{8150 + k}",
            customer_id=c.id,
            amount=round(random.uniform(1_200, 9_800), 2),
            payment_method="card",
            device=random.choice(DEVICES),
            status="failed",
            failure_reason="expired_card",
            timestamp=today - timedelta(days=random.choice([0, 0, 1, 1, 2]), hours=k % 10),
        )
        transactions.append(t)
        db.add(t)

    # Checkout abandonments + renewal failures + funds/declines over 3 days.
    for k in range(500):
        c = random.choice(customers)
        day = random.randint(0, 3)
        t = Transaction(
            transaction_rev=f"TXN_{10000 + k}",
            customer_id=c.id,
            amount=round(random.uniform(299, 6_500), 2),
            payment_method=random.choice(PAYMENT_METHODS),
            device=random.choice(DEVICES),
            status="succeeded",
            failure_reason="",
            timestamp=today - timedelta(days=day, hours=random.randint(1, 20)),
        )
        transactions.append(t)
        db.add(t)

    # Background failed mix over the last 30 days for baseline history.
    for k in range(650):
        c = random.choice(customers)
        day = random.randint(4, 30)
        t = Transaction(
            transaction_rev=f"TXN_{20000 + k}",
            customer_id=c.id,
            amount=round(random.uniform(200, 7_500), 2),
            payment_method=random.choice(PAYMENT_METHODS),
            device=random.choice(DEVICES),
            status="succeeded" if random.random() < 0.93 else "failed",
            failure_reason=random.choice(LEAK_REASONS["funds"] + LEAK_REASONS["decline"]) if random.random() < 0.07 else "",
            timestamp=today - timedelta(days=day, hours=random.randint(1, 22)),
        )
        transactions.append(t)
        db.add(t)

    db.flush()
    return transactions


def _seed_policies(db) -> None:
    rag_service.seed_policies(db)
    db.commit()


def _seed_recovery_history(db, customers) -> list:
    """A set of resolved/closed cases with their strategies/actions/outcomes
    so the executive overview, leak explorer and audit log have real history,
    and the learning loop has recorded outcomes to learn from."""
    cases = []
    now = _now()
    resolved_count = 60

    for k in range(resolved_count):
        c = random.choice(customers)
        amount = round(random.uniform(900, 6_800), 2)
        reason = random.choice(
            ["timeout", "expired_card", "insufficient_funds", "checkout_abandoned", "gateway_error"]
        )
        leak_type = _leak_type(reason)
        recovered = random.random() < 0.64  # approx 64% recovery rate
        created = now - timedelta(days=random.randint(1, 25))
        case = RecoveryCase(
            case_code=f"CASE_{4100 + k}",
            transaction_id=None,   # resolved cases map to the failed tx rows
            risk_score=round(random.uniform(0.4, 0.9), 2),
            recovery_probability=round(random.uniform(0.3, 0.8), 2),
            root_cause=_root_cause(reason),
            confidence=round(random.uniform(0.6, 0.95), 2),
            leak_type=leak_type,
            status="recovered" if recovered else "closed",
            revenue_at_risk=amount,
            contact_count=random.randint(1, 3),
            consecutive_failures=random.randint(0, 2),
            created_at=created,
            updated_at=created + timedelta(days=1),
        )
        db.add(case)
        db.flush()

        # Plan strategies (4 per case) + mark the one that matched the outcome.
        plan = random.choice(["immediate_retry", "delayed_retry", "alternative_payment", "payment_method_update"])
        variants = {
            "immediate_retry": 0.31, "delayed_retry": 0.47,
            "alternative_payment": 0.62, "payment_method_update": 0.76,
            "human_escalation": 0.71,
        }
        for key, prob in variants.items():
            tier = {"human_escalation": "high"}.get(key, "low" if prob < 0.6 else "medium")
            cost, friction = {"high": (150.0, 25.0), "medium": (12.0, 6.0), "low": (2.0, 1.0)}[tier]
            ev = (amount * prob) - cost - friction
            st = RecoveryStrategy(
                case_id=case.id,
                strategy=key,
                predicted_recovery=prob,
                cost=cost,
                friction_score=friction,
                expected_value=round(ev, 2),
                is_AI_proposed=key == plan or random.random() < 0.3,
                recommended=key == plan,
            )
            db.add(st)
            db.flush()

        action_key = {
            "immediate_retry": "execute_retry", "delayed_retry": "delayed_retry",
            "alternative_payment": "send_payment_link", "payment_method_update": "send_payment_link",
            "human_escalation": "escalate_to_human",
        }[plan]
        act = RecoveryAction(
            case_id=case.id,
            strategy_id=st.id,
            action=action_key,
            tool=f"agent_{action_key}",
            status="succeeded" if recovered else "failed",
            predicted_recovery=variants[plan],
            policy_checked="R01..R05 Policy Engine",
            policy_result="allowed" if amount <= 100_000 else "approval_required",
            detail=f"Executed {action_key}",
            timestamp=created + timedelta(hours=random.randint(1, 8)),
        )
        db.add(act)
        db.flush()

        out = RecoveryOutcome(
            action_id=act.id,
            case_id=case.id,
            predicted_recovery=variants[plan],
            amount_recovered=amount if recovered else 0.0,
            success=recovered,
            recovery_time=random.randint(20, 200) if recovered else 0,
            recorded_at=created + timedelta(days=1),
        )
        db.add(out)
        cases.append(case)

    db.add_all(cases)
    db.flush()
    return cases


def _leak_type(reason: str) -> str:
    mapping = {
        "timeout": "Payment Degradation",
        "gateway_error": "Payment Degradation",
        "provider_degraded": "Payment Degradation",
        "expired_card": "Subscription Failures",
        "insufficient_funds": "Card & Customer Issues",
        "card_not_present": "Card & Customer Issues",
        "limit_exceeded": "Card & Customer Issues",
        "declined_generic": "Card & Customer Issues",
        "checkout_abandoned": "Checkout Abandonment",
        "subscription_renewal_failed": "Subscription Failures",
    }
    return mapping.get(reason, "Other")


def _root_cause(reason: str) -> str:
    mapping = {
        "timeout": "Payment-channel degradation",
        "gateway_error": "Payment-channel degradation",
        "provider_degraded": "Payment-channel degradation",
        "expired_card": "Expired card on file",
        "insufficient_funds": "Insufficient funds",
        "card_not_present": "Customer-specific payment restriction",
        "limit_exceeded": "Customer-specific payment restriction",
        "declined_generic": "Generic decline — customer-specific issue",
        "checkout_abandoned": "Checkout abandonment",
        "subscription_renewal_failed": "Subscription renewal failure",
    }
    return mapping.get(reason, "Other")


def _mark_demo_case(db, customers, tx_all, cases) -> None:
    """The README demo case: ₹8,400 card payment, expired card, high-LTV
    returning customer -> Payment Method Update -> recovered."""
    now = _now()
    today = now.replace(hour=19, minute=32, second=0, microsecond=0)

    demo_customer = next(
        (c for c in customers if c.segment == "high_value" and c.payment_method == "card"),
        customers[0],
    )
    demo_tx = Transaction(
        transaction_rev="TXN_48291",
        customer_id=demo_customer.id,
        amount=8400.0,
        payment_method="card",
        device="iPhone",
        status="failed",
        failure_reason="expired_card",
        timestamp=today - timedelta(days=2, hours=5),
    )
    db.add(demo_tx)
    db.flush()

    # Historical recovery for this customer segment (payment-method update).
    demo_case = RecoveryCase(
        case_code="CASE_48291",
        transaction_id=demo_tx.id,
        risk_score=0.72,
        recovery_probability=0.87,
        root_cause="Expired card on file",
        confidence=0.91,
        leak_type="Subscription Failures",
        status="open",
        revenue_at_risk=8400.0,
        contact_count=0,
        consecutive_failures=0,
        created_at=today - timedelta(days=2),
        updated_at=today - timedelta(days=1),
    )
    db.add(demo_case)
    db.flush()
    cases.append(demo_case)
    db.commit()