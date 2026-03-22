"""
main.py — FastAPI application entry point.

Architecture
────────────
  ┌─────────────────────────────────────────┐
  │  HTTP / WebSocket clients               │
  └──────────┬──────────────────────────────┘
             │
  ┌──────────▼──────────────────────────────┐
  │  FastAPI (main.py)                      │
  │   REST endpoints + WS broadcaster       │
  └──────┬──────────────┬───────────────────┘
         │              │
  ┌──────▼──────┐  ┌────▼────────────────────┐
  │ ICUScheduler│  │ PatientDataStore (RAM)  │
  └─────────────┘  └────────┬────────────────┘
                             │
              ┌──────────────▼──────────────────┐
              │ PatientMonitorThread × N (OS)   │
              │  (one thread per ICU patient)   │
              └──────────────┬──────────────────┘
                             │
                   ┌─────────▼──────────┐
                   │  AlertManager      │
                   │  (consumer thread) │
                   └─────────┬──────────┘
                             │
                      ┌──────▼──────┐
                      │  SQLite DB  │
                      └─────────────┘
"""

from __future__ import annotations

import asyncio
import json
import logging
import logging.config
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

import uvicorn
from fastapi import (
    Depends, FastAPI, HTTPException, Query, WebSocket,
    WebSocketDisconnect, status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import config
from alerts import AlertManager
from database import (
    get_db, get_db_session, init_db, save_alert, save_vital_record,
)
from models import (
    AlertSchema, PatientSchema, PatientStatus, PatientVitalsSnapshot,
    SeverityLevel, VitalReading,
)
from scheduler import ICUScheduler
from simulator import ICUSimulator, PatientDataStore

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(level=config.LOG_LEVEL, format=config.LOG_FORMAT)
log = logging.getLogger("icu.main")


# ---------------------------------------------------------------------------
# Global singletons  (initialised inside lifespan)
# ---------------------------------------------------------------------------

store:         PatientDataStore
simulator:     ICUSimulator
scheduler:     ICUScheduler
alert_manager: AlertManager


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------

class ConnectionManager:
    def __init__(self) -> None:
        self._connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.append(ws)
        log.info("WS client connected. Total: %d", len(self._connections))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections = [c for c in self._connections if c is not ws]
        log.info("WS client disconnected. Total: %d", len(self._connections))

    async def broadcast(self, data: dict) -> None:
        dead: List[WebSocket] = []
        async with self._lock:
            targets = list(self._connections)
        for ws in targets:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


ws_manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Background broadcaster (asyncio task, runs inside uvicorn event loop)
# ---------------------------------------------------------------------------

async def vitals_broadcaster() -> None:
    """Push full vitals snapshots to all connected WS clients every 2 s."""
    while True:
        await asyncio.sleep(config.WS_BROADCAST_INTERVAL)
        try:
            states     = store.get_all()
            queue_snap = {e.patient_id: e.priority for e in scheduler.get_queue()}
            payload    = []
            for state in states:
                if state.latest_vitals is None:
                    continue
                patient_dict = {
                    "id":         state.patient_id,
                    "name":       state.patient_name,
                    "age":        state.age,
                    "bed_number": state.bed_number,
                    "diagnosis":  state.diagnosis,
                    "status":     state.status.value,
                }
                vitals_dict = state.latest_vitals.model_dump()
                vitals_dict["timestamp"] = vitals_dict["timestamp"].isoformat()
                vitals_dict["severity"]  = vitals_dict["severity"].value

                recent = alert_manager.get_recent_alerts(limit=200)
                patient_alerts = [
                    {
                        "id":           a.id,
                        "patient_id":   a.patient_id,
                        "patient_name": a.patient_name,
                        "bed_number":   a.bed_number,
                        "timestamp":    a.timestamp.isoformat(),
                        "severity":     a.severity.value,
                        "vital_name":   a.vital_name,
                        "vital_value":  a.vital_value,
                        "message":      a.message,
                        "acknowledged": a.acknowledged,
                    }
                    for a in recent
                    if a.patient_id == state.patient_id
                ][:5]

                payload.append({
                    "patient":  patient_dict,
                    "vitals":   vitals_dict,
                    "alerts":   patient_alerts,
                    "priority": queue_snap.get(state.patient_id, 0),
                })

            if payload:
                await ws_manager.broadcast({"type": "vitals_update", "data": payload})
        except Exception as exc:
            log.exception("Broadcaster error: %s", exc)


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global store, simulator, scheduler, alert_manager

    log.info("━━━━━━━━━ ICU Monitoring System Starting ━━━━━━━━━")

    # 1. Database
    init_db()

    # 2. Shared state
    store = PatientDataStore()

    # 3. Alert manager (needs store before simulator)
    def _db_alert_write(alert_dict: dict) -> None:
        with get_db() as db:
            save_alert(db, alert_dict)

    alert_manager = AlertManager(
        patient_lookup=store.get,
        db_write_cb=_db_alert_write,
        on_alert_cb=None,   # WS push handled by broadcaster
    )
    alert_manager.start()

    # 4. Simulator
    def _db_vital_write(patient_id: int, vitals_dict: dict) -> None:
        with get_db() as db:
            save_vital_record(db, patient_id, vitals_dict)

    simulator = ICUSimulator(
        store=store,
        alert_callback=alert_manager.enqueue_alert,
        db_write_callback=_db_vital_write,
    )

    # Load patients from DB
    with get_db() as db:
        from models import PatientORM
        patients = db.query(PatientORM).all()
        # Detach so they can be used outside session
        patient_list = [
            type("P", (), {
                "id": p.id, "name": p.name, "age": p.age,
                "bed_number": p.bed_number, "diagnosis": p.diagnosis,
            })()
            for p in patients
        ]

    simulator.load_patients(patient_list)   # type: ignore[arg-type]
    simulator.start()

    # 5. Scheduler
    scheduler = ICUScheduler(store=store)
    scheduler.start()

    # 6. Asyncio broadcaster task
    broadcaster_task = asyncio.create_task(vitals_broadcaster())

    log.info("━━━━━━━━━ System fully operational ━━━━━━━━━")

    yield  # ← server runs here

    log.info("━━━━━━━━━ ICU Monitoring System Shutting Down ━━━━━━━━━")
    broadcaster_task.cancel()
    simulator.stop()
    scheduler.stop()
    alert_manager.stop()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Real-Time Smart ICU Monitoring System",
    description="FAANG-level ICU monitoring with multithreaded simulation, "
                "priority scheduling, real-time WebSocket updates, and REST API.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@app.get("/", tags=["Health"])
def root():
    return {"status": "operational", "system": "ICU Monitoring System", "version": "1.0.0"}


@app.get("/health", tags=["Health"])
def health():
    return {
        "status": "healthy",
        "patients_monitored": len(store.get_all()),
        "timestamp": datetime.utcnow().isoformat(),
    }


# ---------- Patients ----------

@app.get("/api/patients", response_model=List[PatientSchema], tags=["Patients"])
def list_patients(db: Session = Depends(get_db_session)):
    from models import PatientORM
    return db.query(PatientORM).all()


@app.get("/api/patients/{patient_id}", tags=["Patients"])
def get_patient(patient_id: int, db: Session = Depends(get_db_session)):
    from models import PatientORM
    patient = db.query(PatientORM).filter(PatientORM.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


# ---------- Vitals ----------

@app.get("/api/vitals", tags=["Vitals"])
def get_all_vitals():
    """Current vitals snapshot for every patient."""
    states = store.get_all()
    result = []
    for s in states:
        if s.latest_vitals:
            v = s.latest_vitals
            result.append({
                "patient_id":   s.patient_id,
                "patient_name": s.patient_name,
                "bed_number":   s.bed_number,
                "status":       s.status.value,
                "vitals": {
                    "heart_rate":       v.heart_rate,
                    "systolic_bp":      v.systolic_bp,
                    "diastolic_bp":     v.diastolic_bp,
                    "spo2":             v.spo2,
                    "temperature":      v.temperature,
                    "respiratory_rate": v.respiratory_rate,
                    "severity":         v.severity.value,
                    "timestamp":        v.timestamp.isoformat(),
                },
            })
    return result


@app.get("/api/vitals/{patient_id}", tags=["Vitals"])
def get_patient_vitals(patient_id: int):
    state = store.get(patient_id)
    if not state:
        raise HTTPException(status_code=404, detail="Patient not found in monitor")
    if not state.latest_vitals:
        return {"message": "No vitals yet", "patient_id": patient_id}
    v = state.latest_vitals
    return {
        "patient_id":   patient_id,
        "patient_name": state.patient_name,
        "bed_number":   state.bed_number,
        "vitals":       v.model_dump(),
        "history":      [r.model_dump() for r in state.history_list()[-20:]],
    }


@app.get("/api/vitals/{patient_id}/history", tags=["Vitals"])
def get_vital_history(patient_id: int, limit: int = Query(50, le=200)):
    state = store.get(patient_id)
    if not state:
        raise HTTPException(status_code=404, detail="Patient not found")
    history = state.history_list()[-limit:]
    return [r.model_dump() for r in history]


# ---------- Alerts ----------

@app.get("/api/alerts", tags=["Alerts"])
def get_alerts(
    limit:    int            = Query(50, le=500),
    severity: Optional[str] = Query(None, description="NORMAL|LOW|MEDIUM|CRITICAL"),
):
    alerts = alert_manager.get_recent_alerts(limit=limit)
    if severity:
        try:
            sev = SeverityLevel(severity.upper())
            alerts = [a for a in alerts if a.severity == sev]
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}")
    return alerts


@app.get("/api/alerts/critical", tags=["Alerts"])
def get_critical_alerts():
    return alert_manager.get_critical_alerts()


@app.post("/api/alerts/{alert_id}/acknowledge", tags=["Alerts"])
def acknowledge_alert(alert_id: int):
    ok = alert_manager.acknowledge(alert_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"acknowledged": True, "alert_id": alert_id}


# ---------- Scheduler / Priority ----------

@app.get("/api/scheduler/queue", tags=["Scheduler"])
def get_priority_queue():
    """Returns patients sorted by triage priority (highest first)."""
    queue_entries = scheduler.get_queue()
    return [
        {
            "rank":         i + 1,
            "patient_id":   e.patient_id,
            "patient_name": e.patient_name,
            "bed_number":   e.bed_number,
            "status":       e.status.value,
            "severity":     e.severity.value,
            "priority":     e.priority,
        }
        for i, e in enumerate(queue_entries)
    ]


# ---------- Statistics ----------

@app.get("/api/stats", tags=["Statistics"])
def get_stats():
    states = store.get_all()
    counts = {s.value: 0 for s in PatientStatus}
    for s in states:
        counts[s.status.value] += 1
    all_alerts = alert_manager.get_recent_alerts(500)
    return {
        "total_patients":    len(states),
        "patient_status":    counts,
        "total_alerts":      len(all_alerts),
        "critical_alerts":   sum(1 for a in all_alerts if a.severity == SeverityLevel.CRITICAL),
        "medium_alerts":     sum(1 for a in all_alerts if a.severity == SeverityLevel.MEDIUM),
        "low_alerts":        sum(1 for a in all_alerts if a.severity == SeverityLevel.LOW),
        "server_time":       datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws/vitals")
async def websocket_vitals(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; data is pushed by broadcaster task
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.API_HOST,
        port=config.API_PORT,
        reload=False,
        log_level=config.LOG_LEVEL.lower(),
    )
