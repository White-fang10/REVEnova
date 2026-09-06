"""Unit tests for deterministic Stopping Rules."""
from datetime import datetime, timedelta

from app.modules.stopping_rules import contacts_within_7d, should_stop


def test_no_stop_on_healthy_case():
    d = should_stop(consecutive_failures=0, recovery_probability=0.9, contacts_in_7d=0)
    assert d.should_stop is False


def test_stop_after_three_consecutive_failures():
    d = should_stop(consecutive_failures=3, recovery_probability=0.8, contacts_in_7d=0)
    assert d.should_stop is True
    assert d.rule_id == "S01"


def test_stop_below_min_probability():
    d = should_stop(consecutive_failures=0, recovery_probability=0.05, contacts_in_7d=0)
    assert d.should_stop is True
    assert d.rule_id == "S02"


def test_stop_at_three_contacts():
    d = should_stop(consecutive_failures=0, recovery_probability=0.9, contacts_in_7d=3)
    assert d.should_stop is True
    assert d.rule_id == "S03"


def test_priority_consecutive_failures_over_others():
    d = should_stop(consecutive_failures=4, recovery_probability=0.02, contacts_in_7d=5)
    assert d.rule_id == "S01"


def test_no_stop_below_limits():
    d = should_stop(consecutive_failures=2, recovery_probability=0.15, contacts_in_7d=2)
    assert d.should_stop is False


def test_contacts_within_7d():
    now = datetime.utcnow()
    times = [
        now - timedelta(days=1),
        now - timedelta(days=3),
        now - timedelta(days=10),  # outside window
    ]
    assert contacts_within_7d(times, now=now) == 2


def test_custom_thresholds():
    assert should_stop(consecutive_failures=2, max_consecutive_failures=2).should_stop is True
    assert should_stop(recovery_probability=0.2, min_probability=0.3).should_stop is True
    assert should_stop(contacts_in_7d=2, max_contacts=2).should_stop is True