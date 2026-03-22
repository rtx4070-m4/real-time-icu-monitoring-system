"""
simulator.py — Real-time vital signs simulator using OS-level threading.

Each patient runs in its own daemon thread, generating realistic vitals
every SIMULATION_INTERVAL_SEC seconds.  A shared thread-safe store
(PatientDataStore) acts as the in-memory state layer.

Design notes
────────────
  • threading.Thread per patient  (OS threads → true parallelism for I/O)
  • threading.RLock  guards the shared dict  (reentrant so same thread can
    re-acquire while holding the lock, e.g. during cascading updates)
  • threading.Event  used for clean shutdown signalling
  • Condition variables signal the scheduler when a critical reading arrives
"""

from __future__ import annotations

import logging
import math
import random
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Deque, Dict, List, Optional

import config
from models import PatientORM, PatientStatus, SeverityLevel, VitalReading

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Vital-sign baseline profiles per diagnosis
# ---------------------------------------------------------------------------

DIAGNOSIS_PROFILES: Dict[str, Dict[str, tuple]] = {
    "Acute MI":               {"heart_rate": (90, 15),  "spo2": (93, 3)},
    "Pneumonia":              {"spo2": (91, 4),          "respiratory_rate": (22, 4)},
    "Stroke":                 {"systolic_bp": (160, 20), "heart_rate": (85, 10)},
    "Sepsis":                 {"heart_rate": (105, 20),  "temperature": (38.5, 0.8)},
    "COPD Exacerbation":      {"spo2": (89, 5),          "respiratory_rate": (24, 5)},
    "Pulmonary Embolism":     {"respiratory_rate": (26, 6), "heart_rate": (110, 15)},
    "Renal Failure":          {"systolic_bp": (150, 15), "diastolic_bp": (95, 10)},
    "Trauma":                 {"heart_rate": (115, 25),  "systolic_bp": (100, 20)},
    "DEFAULT":                {},
}

NORMAL_BASELINES = {
    "heart_rate":       (75,  8),
    "systolic_bp":      (120, 10),
    "diastolic_bp":     (80,  8),
    "spo2":             (98,  1.5),
    "temperature":      (37.0, 0.3),
    "respiratory_rate": (16,  2),
}

# Limits to clamp random values to physiologically plausible ranges
PHYSIOLOGICAL_LIMITS = {
    "heart_rate":       (20,  220),
    "systolic_bp":      (50,  260),
    "diastolic_bp":     (30,  150),
    "spo2":             (60,  100),
    "temperature":      (32,  42),
    "respiratory_rate": (4,   60),
}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _classify_severity(vitals: dict) -> SeverityLevel:
    """Return the worst severity across all vitals."""
    worst = SeverityLevel.NORMAL

    checks = {
        "heart_rate":       (config.VITAL_THRESHOLDS["heart_rate"],       vitals.get("heart_rate")),
        "systolic_bp":      (config.VITAL_THRESHOLDS["systolic_bp"],      vitals.get("systolic_bp")),
        "diastolic_bp":     (config.VITAL_THRESHOLDS["diastolic_bp"],     vitals.get("diastolic_bp")),
        "spo2":             (config.VITAL_THRESHOLDS["spo2"],             vitals.get("spo2")),
        "temperature":      (config.VITAL_THRESHOLDS["temperature"],      vitals.get("temperature")),
        "respiratory_rate": (config.VITAL_THRESHOLDS["respiratory_rate"], vitals.get("respiratory_rate")),
    }

    severity_rank = {
        SeverityLevel.NORMAL:   0,
        SeverityLevel.LOW:      1,
        SeverityLevel.MEDIUM:   2,
        SeverityLevel.CRITICAL: 3,
    }

    for vital_name, (thresholds, value) in checks.items():
        if value is None:
            continue
        normal_min, normal_max = thresholds["normal"]
        low_min,    low_max    = thresholds["low"]
        medium_min, medium_max = thresholds["medium"]

        if normal_min <= value <= normal_max:
            sev = SeverityLevel.NORMAL
        elif low_min <= value <= low_max:
            sev = SeverityLevel.LOW
        elif medium_min <= value <= medium_max:
            sev = SeverityLevel.MEDIUM
        else:
            sev = SeverityLevel.CRITICAL

        if severity_rank[sev] > severity_rank[worst]:
            worst = sev

    return worst


# ---------------------------------------------------------------------------
# Per-patient state
# ---------------------------------------------------------------------------

@dataclass
class PatientState:
    patient_id:   int
    patient_name: str
    bed_number:   str
    diagnosis:    str
    age:          int
    status:       PatientStatus = PatientStatus.STABLE

    latest_vitals: Optional[VitalReading] = None
    history:       Deque[VitalReading]    = field(default_factory=lambda: deque(maxlen=config.MAX_HISTORY_POINTS))
    priority_score: int = 0               # set by scheduler

    # Simulated waveform phases (for smoother, correlated readings)
    _phase: float = field(default_factory=lambda: random.uniform(0, 2 * math.pi))

    def push_vitals(self, reading: VitalReading) -> None:
        self.latest_vitals = reading
        self.history.append(reading)

    def history_list(self) -> List[VitalReading]:
        return list(self.history)


# ---------------------------------------------------------------------------
# Thread-safe shared store
# ---------------------------------------------------------------------------

class PatientDataStore:
    """Central in-memory store; all access is protected by an RLock."""

    def __init__(self) -> None:
        self._lock: threading.RLock = threading.RLock()
        self._patients: Dict[int, PatientState] = {}
        # Condition variable for scheduler to wait on critical events
        self.critical_event: threading.Condition = threading.Condition(self._lock)

    def register(self, state: PatientState) -> None:
        with self._lock:
            self._patients[state.patient_id] = state

    def update(self, patient_id: int, reading: VitalReading, status: PatientStatus) -> None:
        with self._lock:
            if patient_id in self._patients:
                self._patients[patient_id].push_vitals(reading)
                self._patients[patient_id].status = status
                if reading.severity == SeverityLevel.CRITICAL:
                    self.critical_event.notify_all()

    def get_all(self) -> List[PatientState]:
        with self._lock:
            return list(self._patients.values())

    def get(self, patient_id: int) -> Optional[PatientState]:
        with self._lock:
            return self._patients.get(patient_id)

    def set_priority(self, patient_id: int, score: int) -> None:
        with self._lock:
            if patient_id in self._patients:
                self._patients[patient_id].priority_score = score


# ---------------------------------------------------------------------------
# Patient monitor thread
# ---------------------------------------------------------------------------

class PatientMonitorThread(threading.Thread):
    """
    Daemon thread that continuously generates vital signs for ONE patient.

    Uses a sinusoidal drift model so readings are correlated over time
    (avoids pure white noise which would look unrealistic).
    """

    def __init__(
        self,
        state: PatientState,
        store: PatientDataStore,
        alert_callback: Callable[[int, str, float, SeverityLevel], None],
        stop_event: threading.Event,
        db_write_callback: Optional[Callable[[int, dict], None]] = None,
    ) -> None:
        super().__init__(
            name=f"patient-{state.patient_id}-{state.bed_number}",
            daemon=True,
        )
        self.state            = state
        self.store            = store
        self.alert_callback   = alert_callback
        self.stop_event       = stop_event
        self.db_write_cb      = db_write_callback
        self._tick: int       = 0

        # Build baseline for this patient's diagnosis
        profile = DIAGNOSIS_PROFILES.get(state.diagnosis, DIAGNOSIS_PROFILES["DEFAULT"])
        self._baselines: Dict[str, tuple] = {}
        for vital, default in NORMAL_BASELINES.items():
            self._baselines[vital] = profile.get(vital, default)

        log.info(
            "[%s] Monitor thread initialised for patient '%s' (diagnosis: %s)",
            self.name, state.patient_name, state.diagnosis,
        )

    # ------------------------------------------------------------------

    def _generate_vital(self, vital: str) -> float:
        mean, std = self._baselines[vital]
        # Slow sinusoidal trend + Gaussian noise
        drift = math.sin(self.state._phase + self._tick * 0.15) * std * 0.5
        noise = random.gauss(0, std * 0.3)
        value = mean + drift + noise
        lo, hi = PHYSIOLOGICAL_LIMITS[vital]
        return round(_clamp(value, lo, hi), 1)

    def _generate_reading(self) -> VitalReading:
        raw = {v: self._generate_vital(v) for v in NORMAL_BASELINES}
        severity = _classify_severity(raw)
        return VitalReading(**raw, severity=severity, timestamp=datetime.utcnow())

    def _status_from_severity(self, sev: SeverityLevel) -> PatientStatus:
        return {
            SeverityLevel.NORMAL:   PatientStatus.STABLE,
            SeverityLevel.LOW:      PatientStatus.STABLE,
            SeverityLevel.MEDIUM:   PatientStatus.WATCH,
            SeverityLevel.CRITICAL: PatientStatus.CRITICAL,
        }[sev]

    # ------------------------------------------------------------------

    def run(self) -> None:
        log.info("[%s] Starting simulation loop.", self.name)
        while not self.stop_event.is_set():
            try:
                reading = self._generate_reading()
                status  = self._status_from_severity(reading.severity)

                self.store.update(self.state.patient_id, reading, status)

                # Fire alert for anything above NORMAL
                if reading.severity != SeverityLevel.NORMAL:
                    # Find which vital is worst
                    self._fire_alerts(reading)

                # Async-style DB write via callback (decouples I/O from sim thread)
                if self.db_write_cb:
                    vitals_dict = reading.model_dump()
                    vitals_dict["severity"] = reading.severity.value
                    vitals_dict.pop("timestamp", None)
                    self.db_write_cb(self.state.patient_id, vitals_dict)

                self._tick += 1
                self.stop_event.wait(timeout=config.SIMULATION_INTERVAL_SEC)

            except Exception as exc:
                log.exception("[%s] Unexpected error in sim loop: %s", self.name, exc)
                self.stop_event.wait(timeout=config.SIMULATION_INTERVAL_SEC)

        log.info("[%s] Simulation thread exiting.", self.name)

    def _fire_alerts(self, reading: VitalReading) -> None:
        """Raise alert for each vital that is out of normal range."""
        thresholds = config.VITAL_THRESHOLDS
        vitals_map = {
            "Heart Rate":        reading.heart_rate,
            "Systolic BP":       reading.systolic_bp,
            "Diastolic BP":      reading.diastolic_bp,
            "SpO₂":              reading.spo2,
            "Temperature":       reading.temperature,
            "Respiratory Rate":  reading.respiratory_rate,
        }
        key_map = {
            "Heart Rate": "heart_rate", "Systolic BP": "systolic_bp",
            "Diastolic BP": "diastolic_bp", "SpO₂": "spo2",
            "Temperature": "temperature", "Respiratory Rate": "respiratory_rate",
        }
        for label, value in vitals_map.items():
            key = key_map[label]
            norm_min, norm_max = thresholds[key]["normal"]
            if not (norm_min <= value <= norm_max):
                self.alert_callback(
                    self.state.patient_id,
                    label,
                    value,
                    reading.severity,
                )


# ---------------------------------------------------------------------------
# Simulator (orchestrator)
# ---------------------------------------------------------------------------

class ICUSimulator:
    """
    Orchestrates all patient threads.  Called once at startup.
    """

    def __init__(
        self,
        store: PatientDataStore,
        alert_callback: Callable,
        db_write_callback: Optional[Callable] = None,
    ) -> None:
        self.store            = store
        self.alert_callback   = alert_callback
        self.db_write_cb      = db_write_callback
        self._stop_event      = threading.Event()
        self._threads: List[PatientMonitorThread] = []

    def load_patients(self, patients: List[PatientORM]) -> None:
        """Register all patients with the store and spin up threads."""
        for p in patients:
            state = PatientState(
                patient_id=p.id,
                patient_name=p.name,
                bed_number=p.bed_number,
                diagnosis=p.diagnosis or "DEFAULT",
                age=p.age,
            )
            self.store.register(state)
            thread = PatientMonitorThread(
                state=state,
                store=self.store,
                alert_callback=self.alert_callback,
                stop_event=self._stop_event,
                db_write_callback=self.db_write_cb,
            )
            self._threads.append(thread)
        log.info("ICUSimulator: %d patient threads prepared.", len(self._threads))

    def start(self) -> None:
        for t in self._threads:
            t.start()
        log.info("ICUSimulator: All threads running.")

    def stop(self) -> None:
        log.info("ICUSimulator: Stopping all threads …")
        self._stop_event.set()
        for t in self._threads:
            t.join(timeout=5)
        log.info("ICUSimulator: All threads stopped.")
