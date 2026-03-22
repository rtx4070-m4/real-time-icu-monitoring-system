"""
alerts.py — Thread-safe alert manager with severity routing and deduplication.

Design
──────
  • AlertManager runs as a thread consuming from a queue.Queue (producer-consumer)
  • Simulator threads (producers) call enqueue_alert() → non-blocking
  • AlertManager thread (consumer) processes, deduplicates, persists, and
    notifies WebSocket broadcaster
  • Deduplication window: same patient + same vital won't fire again within
    DEDUP_WINDOW_SEC (avoids alert fatigue)
  • In-memory ring buffer of MAX_ALERT_HISTORY alerts for fast API reads
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections import deque
from datetime import datetime
from typing import Callable, Deque, Dict, Optional, Tuple

import config
from models import AlertSchema, SeverityLevel

log = logging.getLogger(__name__)

DEDUP_WINDOW_SEC: int = 10   # seconds between identical alerts for same patient+vital

SEVERITY_MESSAGES = {
    SeverityLevel.LOW:      "⚠ {vital} slightly out of range: {value}",
    SeverityLevel.MEDIUM:   "⛔ {vital} at concerning level: {value}",
    SeverityLevel.CRITICAL: "🚨 CRITICAL: {vital} at dangerous level: {value} — IMMEDIATE ATTENTION REQUIRED",
}


class AlertManager(threading.Thread):
    """Consumes alert events from a queue and manages history."""

    def __init__(
        self,
        patient_lookup: Callable[[int], Optional[object]],  # store.get()
        db_write_cb: Optional[Callable[[dict], None]] = None,
        on_alert_cb: Optional[Callable[[AlertSchema], None]] = None,  # WS notifier
    ) -> None:
        super().__init__(name="alert-manager", daemon=True)
        self._queue: queue.Queue = queue.Queue(maxsize=1000)
        self._stop_event         = threading.Event()
        self._patient_lookup     = patient_lookup
        self._db_write_cb        = db_write_cb
        self._on_alert_cb        = on_alert_cb

        # Ring buffer for recent alerts (thread-safe via lock)
        self._history: Deque[AlertSchema] = deque(maxlen=config.MAX_ALERT_HISTORY)
        self._history_lock = threading.Lock()

        # Deduplication: key=(patient_id, vital_name) → last alert timestamp
        self._dedup: Dict[Tuple[int, str], float] = {}
        self._dedup_lock = threading.Lock()

        self._alert_counter: int = 1

    # ------------------------------------------------------------------
    # Public API (called from simulator threads)
    # ------------------------------------------------------------------

    def enqueue_alert(
        self,
        patient_id: int,
        vital_name: str,
        vital_value: float,
        severity: SeverityLevel,
    ) -> None:
        """Non-blocking: drop silently if queue is full (back-pressure)."""
        try:
            self._queue.put_nowait(
                (patient_id, vital_name, vital_value, severity, time.time())
            )
        except queue.Full:
            log.warning("Alert queue full — dropping alert for patient %d", patient_id)

    # ------------------------------------------------------------------

    def get_recent_alerts(self, limit: int = 50) -> list[AlertSchema]:
        with self._history_lock:
            alerts = list(self._history)
        return sorted(alerts, key=lambda a: a.timestamp, reverse=True)[:limit]

    def get_critical_alerts(self) -> list[AlertSchema]:
        with self._history_lock:
            return [a for a in self._history if a.severity == SeverityLevel.CRITICAL]

    def acknowledge(self, alert_id: int) -> bool:
        with self._history_lock:
            for alert in self._history:
                if alert.id == alert_id:
                    # Pydantic v2: model_copy with update
                    idx = list(self._history).index(alert)
                    self._history[idx] = alert.model_copy(update={"acknowledged": True})
                    return True
        return False

    # ------------------------------------------------------------------

    def stop(self) -> None:
        self._stop_event.set()
        self._queue.put(None)  # sentinel to unblock queue.get()

    # ------------------------------------------------------------------

    def run(self) -> None:
        log.info("[%s] Alert manager started.", self.name)
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=2.0)
            except queue.Empty:
                continue

            if item is None:  # shutdown sentinel
                break

            patient_id, vital_name, vital_value, severity, ts = item
            self._process(patient_id, vital_name, vital_value, severity, ts)

        log.info("[%s] Alert manager stopped.", self.name)

    def _is_duplicate(self, patient_id: int, vital_name: str) -> bool:
        key = (patient_id, vital_name)
        now = time.time()
        with self._dedup_lock:
            last = self._dedup.get(key, 0)
            if now - last < DEDUP_WINDOW_SEC:
                return True
            self._dedup[key] = now
        return False

    def _process(
        self,
        patient_id: int,
        vital_name: str,
        vital_value: float,
        severity: SeverityLevel,
        ts: float,
    ) -> None:
        if self._is_duplicate(patient_id, vital_name):
            return

        state = self._patient_lookup(patient_id)
        if state is None:
            return

        msg_tmpl = SEVERITY_MESSAGES.get(severity, "{vital}: {value}")
        message  = msg_tmpl.format(vital=vital_name, value=vital_value)

        alert = AlertSchema(
            id           = self._alert_counter,
            patient_id   = patient_id,
            patient_name = state.patient_name,
            bed_number   = state.bed_number,
            timestamp    = datetime.utcnow(),
            severity     = severity,
            vital_name   = vital_name,
            vital_value  = vital_value,
            message      = message,
            acknowledged = False,
        )
        self._alert_counter += 1

        with self._history_lock:
            self._history.append(alert)

        log.log(
            logging.CRITICAL if severity == SeverityLevel.CRITICAL else
            logging.WARNING  if severity == SeverityLevel.MEDIUM   else
            logging.INFO,
            "[ALERT] %s | Patient: %s (%s) | %s",
            severity.value, state.patient_name, state.bed_number, message,
        )

        # Persist to DB (non-blocking callback)
        if self._db_write_cb:
            alert_dict = {
                "patient_id":   patient_id,
                "patient_name": state.patient_name,
                "bed_number":   state.bed_number,
                "severity":     severity.value,
                "vital_name":   vital_name,
                "vital_value":  vital_value,
                "message":      message,
            }
            try:
                self._db_write_cb(alert_dict)
            except Exception as exc:
                log.error("DB write failed for alert: %s", exc)

        # Notify WebSocket broadcaster
        if self._on_alert_cb:
            try:
                self._on_alert_cb(alert)
            except Exception as exc:
                log.error("WS notify failed: %s", exc)
