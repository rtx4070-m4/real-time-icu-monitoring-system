"""
scheduler.py — Priority-based ICU scheduler (OS scheduling concepts applied).

Implements a preemptive priority queue scheduler inspired by:
  • Linux CFS (Completely Fair Scheduler)  — aging to prevent starvation
  • Real-time OS POSIX SCHED_FIFO          — critical patients always first

Priority score = severity_weight + age_bonus - wait_penalty
The scheduler runs in its own thread and updates priority_score for every
patient in the shared store every SCHEDULER_TICK_SEC seconds.

Scheduling algorithm
─────────────────────
  1. Score each patient based on their latest vital severity.
  2. Apply an age bonus (patients waiting longer without attention get +1
     every N ticks to prevent starvation — mirrors aging in OS schedulers).
  3. Expose a sorted priority queue so the alert router and dashboard can
     display patients in triage order.
  4. Emit a PREEMPTION event when a non-critical patient is bumped by a
     newly-critical one (logged; extendable to nurse pager integration).
"""

from __future__ import annotations

import heapq
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional

import config
from models import PatientStatus, SeverityLevel
from simulator import PatientDataStore, PatientState

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Severity → base priority weight
# ---------------------------------------------------------------------------

SEVERITY_WEIGHTS = {
    SeverityLevel.NORMAL:   0,
    SeverityLevel.LOW:      10,
    SeverityLevel.MEDIUM:   30,
    SeverityLevel.CRITICAL: 100,
}

AGE_BONUS_INTERVAL: int = 5   # ticks before starvation bonus applies
AGE_BONUS_VALUE: int    = 2   # score added per interval


# ---------------------------------------------------------------------------
# Priority queue entry
# ---------------------------------------------------------------------------

@dataclass(order=True)
class SchedulerEntry:
    """
    Negated priority so Python's min-heap behaves as a max-heap.
    patient_id is tie-breaker (lower bed number = lower ID = first).
    """
    neg_priority: int              = field(compare=True)
    patient_id:   int              = field(compare=True)
    patient_name: str              = field(compare=False)
    bed_number:   str              = field(compare=False)
    status:       PatientStatus    = field(compare=False)
    severity:     SeverityLevel    = field(compare=False)
    priority:     int              = field(compare=False)


# ---------------------------------------------------------------------------
# Scheduler thread
# ---------------------------------------------------------------------------

class ICUScheduler(threading.Thread):
    """
    Daemon thread that recalculates patient priorities every tick.

    Public interface
    ─────────────────
      .get_queue()  → List[SchedulerEntry]  sorted highest-priority first
      .stop()       → signals clean shutdown
    """

    def __init__(self, store: PatientDataStore) -> None:
        super().__init__(name="icu-scheduler", daemon=True)
        self.store        = store
        self._stop_event  = threading.Event()
        self._lock        = threading.Lock()
        self._queue: List[SchedulerEntry] = []
        self._tick_counts: dict[int, int] = {}   # patient_id → ticks since last CRITICAL
        self._tick: int   = 0

    # ------------------------------------------------------------------

    def stop(self) -> None:
        self._stop_event.set()

    def get_queue(self) -> List[SchedulerEntry]:
        """Return a snapshot of the priority queue (highest priority first)."""
        with self._lock:
            # Heap is a min-heap; we stored neg_priority so pop gives max
            return sorted(self._queue, key=lambda e: e.neg_priority)

    # ------------------------------------------------------------------

    def _compute_priority(self, state: PatientState) -> int:
        if state.latest_vitals is None:
            return 0

        severity = state.latest_vitals.severity
        base     = SEVERITY_WEIGHTS[severity]

        # Age bonus: if patient has been non-critical for a while, boost slightly
        # to ensure their data isn't perpetually deprioritised in the queue
        wait = self._tick_counts.get(state.patient_id, 0)
        if severity != SeverityLevel.CRITICAL:
            age_bonus = (wait // AGE_BONUS_INTERVAL) * AGE_BONUS_VALUE
        else:
            age_bonus = 0
            self._tick_counts[state.patient_id] = 0  # reset on critical

        # Extra bump for very high/low values (SpO2 < 88 or HR > 150)
        surge = 0
        v = state.latest_vitals
        if v.spo2 < 88:
            surge += 20
        if v.heart_rate > 150 or v.heart_rate < 40:
            surge += 15
        if v.systolic_bp < 70 or v.systolic_bp > 200:
            surge += 15

        return base + age_bonus + surge

    def _rebuild_queue(self) -> None:
        patients = self.store.get_all()
        heap: List[SchedulerEntry] = []
        previous_top: Optional[int] = self._queue[0].patient_id if self._queue else None

        for state in patients:
            priority = self._compute_priority(state)
            self.store.set_priority(state.patient_id, priority)
            self._tick_counts[state.patient_id] = (
                self._tick_counts.get(state.patient_id, 0) + 1
            )
            severity = (
                state.latest_vitals.severity
                if state.latest_vitals
                else SeverityLevel.NORMAL
            )
            entry = SchedulerEntry(
                neg_priority = -priority,
                patient_id   = state.patient_id,
                patient_name = state.patient_name,
                bed_number   = state.bed_number,
                status       = state.status,
                severity     = severity,
                priority     = priority,
            )
            heapq.heappush(heap, entry)

        with self._lock:
            self._queue = heap

        # Detect preemption: new top != old top
        new_top = heap[0].patient_id if heap else None
        if previous_top and new_top and new_top != previous_top:
            top_entry = heap[0]
            log.warning(
                "⚡ SCHEDULER PREEMPTION: Patient '%s' (bed %s, priority=%d) "
                "bumped to top of queue.",
                top_entry.patient_name,
                top_entry.bed_number,
                top_entry.priority,
            )

    # ------------------------------------------------------------------

    def run(self) -> None:
        log.info("[%s] Scheduler started. Tick interval: %.1fs", self.name, config.SCHEDULER_TICK_SEC)
        while not self._stop_event.is_set():
            try:
                self._rebuild_queue()
                log.debug(
                    "[Scheduler tick %d] Top patient: %s",
                    self._tick,
                    self._queue[0].patient_name if self._queue else "none",
                )
                self._tick += 1
            except Exception as exc:
                log.exception("[Scheduler] Error during tick: %s", exc)
            self._stop_event.wait(timeout=config.SCHEDULER_TICK_SEC)
        log.info("[%s] Scheduler stopped.", self.name)
