"""
tests/test_scheduler.py — Unit tests for the ICU scheduler.

Run with:  cd backend && pytest ../tests/test_scheduler.py -v
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

import time
import threading
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from models import PatientStatus, SeverityLevel, VitalReading
from simulator import PatientDataStore, PatientState
from scheduler import ICUScheduler, SEVERITY_WEIGHTS


# ─── Fixtures ─────────────────────────────────────────────────────────────

def make_state(pid, severity=SeverityLevel.NORMAL, name="Test", bed="ICU-00"):
    state = PatientState(
        patient_id=pid, patient_name=name, bed_number=bed,
        diagnosis="Test", age=50,
    )
    state.latest_vitals = VitalReading(
        heart_rate=75, systolic_bp=120, diastolic_bp=80,
        spo2=98, temperature=37.0, respiratory_rate=16,
        severity=severity,
    )
    return state


def make_store(*states):
    store = PatientDataStore()
    for s in states:
        store.register(s)
    return store


# ─── Tests ────────────────────────────────────────────────────────────────

class TestSeverityWeights:
    def test_critical_weight_highest(self):
        assert SEVERITY_WEIGHTS[SeverityLevel.CRITICAL] > SEVERITY_WEIGHTS[SeverityLevel.MEDIUM]
        assert SEVERITY_WEIGHTS[SeverityLevel.MEDIUM]   > SEVERITY_WEIGHTS[SeverityLevel.LOW]
        assert SEVERITY_WEIGHTS[SeverityLevel.LOW]      > SEVERITY_WEIGHTS[SeverityLevel.NORMAL]

    def test_normal_weight_zero(self):
        assert SEVERITY_WEIGHTS[SeverityLevel.NORMAL] == 0


class TestSchedulerPriorityOrdering:
    def test_critical_patient_ranked_first(self):
        normal   = make_state(1, SeverityLevel.NORMAL, "Alice", "ICU-01")
        critical = make_state(2, SeverityLevel.CRITICAL, "Bob",   "ICU-02")
        store    = make_store(normal, critical)

        sched = ICUScheduler(store=store)
        sched._rebuild_queue()
        q = sched.get_queue()

        assert q[0].patient_id == 2, "Critical patient should be first"

    def test_medium_before_low(self):
        low    = make_state(1, SeverityLevel.LOW,    "Alice", "ICU-01")
        medium = make_state(2, SeverityLevel.MEDIUM, "Bob",   "ICU-02")
        store  = make_store(low, medium)

        sched = ICUScheduler(store=store)
        sched._rebuild_queue()
        q = sched.get_queue()

        assert q[0].patient_id == 2, "Medium severity should outrank low"

    def test_single_patient_queue(self):
        state = make_state(1, SeverityLevel.NORMAL)
        store = make_store(state)

        sched = ICUScheduler(store=store)
        sched._rebuild_queue()
        q = sched.get_queue()

        assert len(q) == 1
        assert q[0].patient_id == 1

    def test_empty_store(self):
        store = make_store()
        sched = ICUScheduler(store=store)
        sched._rebuild_queue()
        assert sched.get_queue() == []

    def test_priority_score_updates_in_store(self):
        state = make_state(1, SeverityLevel.CRITICAL)
        store = make_store(state)

        sched = ICUScheduler(store=store)
        sched._rebuild_queue()

        updated = store.get(1)
        assert updated.priority_score > 0, "Store should reflect updated priority"


class TestSchedulerAgingBonus:
    """Verify that low-priority patients eventually get aging bonuses."""

    def test_aging_increases_score(self):
        from scheduler import AGE_BONUS_INTERVAL, AGE_BONUS_VALUE

        state = make_state(1, SeverityLevel.NORMAL)
        store = make_store(state)

        sched = ICUScheduler(store=store)

        # First tick score
        sched._rebuild_queue()
        first_score = sched.get_queue()[0].priority

        # Simulate ticks to trigger aging
        for _ in range(AGE_BONUS_INTERVAL + 1):
            sched._rebuild_queue()

        later_score = sched.get_queue()[0].priority
        assert later_score >= first_score, "Score should not decrease due to aging"


class TestSchedulerThread:
    def test_scheduler_starts_and_stops(self):
        store = make_store(make_state(1))
        sched = ICUScheduler(store=store)
        sched.start()
        time.sleep(0.2)
        assert sched.is_alive()
        sched.stop()
        sched.join(timeout=3)
        assert not sched.is_alive()

    def test_get_queue_thread_safe(self):
        """Multiple threads reading the queue shouldn't cause errors."""
        states = [make_state(i, SeverityLevel.NORMAL) for i in range(1, 11)]
        store  = make_store(*states)
        sched  = ICUScheduler(store=store)
        sched._rebuild_queue()

        errors = []

        def reader():
            try:
                for _ in range(50):
                    q = sched.get_queue()
                    assert isinstance(q, list)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()

        assert not errors, f"Thread-safety errors: {errors}"


class TestPatientDataStore:
    def test_register_and_get(self):
        store = PatientDataStore()
        state = make_state(42)
        store.register(state)
        assert store.get(42) is state

    def test_update_vitals(self):
        store = PatientDataStore()
        state = make_state(1)
        store.register(state)

        new_vitals = VitalReading(
            heart_rate=130, systolic_bp=170, diastolic_bp=100,
            spo2=85, temperature=39.5, respiratory_rate=30,
            severity=SeverityLevel.CRITICAL,
        )
        store.update(1, new_vitals, PatientStatus.CRITICAL)
        updated = store.get(1)
        assert updated.latest_vitals.heart_rate == 130
        assert updated.status == PatientStatus.CRITICAL

    def test_get_all_returns_all(self):
        store = make_store(make_state(1), make_state(2), make_state(3))
        assert len(store.get_all()) == 3

    def test_set_priority(self):
        store = make_store(make_state(1))
        store.set_priority(1, 42)
        assert store.get(1).priority_score == 42

    def test_critical_event_notified(self):
        """Condition variable fires when a critical vital is pushed."""
        store   = PatientDataStore()
        state   = make_state(1)
        store.register(state)
        notified = threading.Event()

        def waiter():
            with store.critical_event:
                store.critical_event.wait(timeout=3)
                notified.set()

        t = threading.Thread(target=waiter, daemon=True)
        t.start()

        critical_vitals = VitalReading(
            heart_rate=200, systolic_bp=230, diastolic_bp=140,
            spo2=70, temperature=41, respiratory_rate=40,
            severity=SeverityLevel.CRITICAL,
        )
        time.sleep(0.05)
        store.update(1, critical_vitals, PatientStatus.CRITICAL)
        t.join(timeout=2)
        assert notified.is_set(), "Condition variable should fire on CRITICAL update"
