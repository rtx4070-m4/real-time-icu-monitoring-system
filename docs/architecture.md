# System Architecture — Real-Time Smart ICU Monitoring System

## High-Level Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                        CLIENT TIER                                │
│  Browser (index.html + app.js + styles.css)                       │
│  ┌───────────────┐          ┌──────────────────────────────────┐  │
│  │  REST Calls   │◄────────►│  WebSocket /ws/vitals            │  │
│  │  /api/*       │          │  ← live push every 2 s          │  │
│  └───────────────┘          └──────────────────────────────────┘  │
└────────────────────────────┬──────────────────────────────────────┘
                             │ HTTP / WS
┌────────────────────────────▼──────────────────────────────────────┐
│                     APPLICATION TIER (FastAPI)                    │
│                                                                   │
│  main.py                                                          │
│  ├── REST Router  (/api/patients, /api/vitals, /api/alerts, …)   │
│  ├── WS endpoint  (/ws/vitals)                                    │
│  └── asyncio task: vitals_broadcaster()  ──────────────────────► │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │             PatientDataStore  (shared memory)            │     │
│  │  • Dict[int, PatientState]    protected by threading.RLock    │
│  │  • Condition variable for CRITICAL event notification    │     │
│  └───────────────┬──────────────────────────────────────────┘     │
│                  │                                                │
│  ┌───────────────▼───────────────────────────┐                   │
│  │        ICUSimulator (orchestrator)        │                   │
│  │  Spawns N PatientMonitorThread (OS threads)                   │
│  │                                           │                   │
│  │  PatientMonitorThread × 8 (daemon)        │                   │
│  │  ├── Sinusoidal drift + Gaussian noise    │                   │
│  │  ├── Diagnosis-aware baselines            │                   │
│  │  ├── _classify_severity()                 │                   │
│  │  ├── alert_callback → AlertManager.enqueue│                   │
│  │  └── db_write_callback → SQLite           │                   │
│  └───────────────────────────────────────────┘                   │
│                                                                   │
│  ┌──────────────────────┐   ┌────────────────────────────────┐   │
│  │   ICUScheduler        │   │   AlertManager                 │   │
│  │   (daemon thread)     │   │   (daemon thread)              │   │
│  │                       │   │                                │   │
│  │  Priority score =     │   │  queue.Queue (producer-consumer│   │
│  │   severity_weight     │   │  Dedup window: 10 s            │   │
│  │   + age_bonus         │   │  Ring buffer: 500 alerts       │   │
│  │   + surge_bonus       │   │  DB write via callback         │   │
│  │                       │   │                                │   │
│  │  Heapq max-heap       │   └────────────────────────────────┘   │
│  └──────────────────────┘                                        │
└───────────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────▼──────────────────────────────────────┐
│                       DATA TIER                                   │
│  SQLite (dev) / PostgreSQL (prod)                                 │
│  Tables: patients | vital_records | alerts                        │
└───────────────────────────────────────────────────────────────────┘
```

---

## Threading Model

### OS Thread Allocation

| Thread | Name | Purpose | Sync primitive |
|--------|------|---------|----------------|
| Main (uvicorn) | main | FastAPI event loop, WebSocket broadcaster | asyncio event loop |
| Patient 1–N | `patient-{id}-{bed}` | Vital sign simulation | threading.Event (stop signal) |
| ICUScheduler | `icu-scheduler` | Priority recalculation every 1s | threading.Condition |
| AlertManager | `alert-manager` | Alert dedup, persistence, routing | queue.Queue |

### Locking Strategy

```
PatientDataStore._lock (threading.RLock)
│
├── store.register()    — write (startup only, no contention)
├── store.update()      — write (per patient thread, ~2s interval)
│   └── critical_event.notify_all()  — fires Condition waiters
├── store.get_all()     — read  (broadcaster, scheduler)
├── store.get()         — read  (alert manager)
└── store.set_priority()— write (scheduler thread)

AlertManager._history_lock (threading.Lock)
├── get_recent_alerts() — read
└── _process()          — write (consumer thread only)

AlertManager._dedup_lock (threading.Lock)
└── _is_duplicate()     — read + conditional write
```

**No deadlock risk:** RLock is reentrant; inner locks (history, dedup) are
never held while acquiring outer lock. Lock acquisition order is consistent.

---

## Scheduling Algorithm

Inspired by Linux CFS (Completely Fair Scheduler) + POSIX SCHED_FIFO:

```
priority_score(patient) =
    SEVERITY_WEIGHTS[latest_severity]          # base: 0/10/30/100
  + floor(wait_ticks / AGE_BONUS_INTERVAL)     # anti-starvation aging
    × AGE_BONUS_VALUE
  + surge_bonus(vitals)                        # SpO2<88 → +20, HR>150 → +15
```

Patients sorted by `priority_score` descending into a max-heap (Python
`heapq` with negated priority). Preemption is detected and logged when the
queue top changes between ticks.

---

## Data Flow

```
Sensor data (simulated)
    │
    ▼
PatientMonitorThread.run()
    │   2 s tick
    ▼
_generate_reading()          ← sinusoidal + Gaussian model
    │
    ├──► PatientDataStore.update()   ← in-memory latest + history
    │
    ├──► alert_callback()            ← non-blocking enqueue
    │       │
    │       ▼
    │    AlertManager._queue  (queue.Queue, size 1000)
    │       │
    │       ▼  consumer thread
    │    _process() → dedup → persist → ring buffer
    │
    └──► db_write_callback()         ← SQLAlchemy + WAL SQLite
             │
             ▼
          vital_records table


Every 2 s:
  asyncio vitals_broadcaster()
      │
      ├── store.get_all()            ← RLock read
      ├── scheduler.get_queue()      ← heapq snapshot
      ├── alert_manager.get_recent_alerts()
      │
      └──► ws_manager.broadcast()   ← push to all WS clients
```

---

## Scaling Strategy

### Vertical (single node)
- Python GIL bypassed by IO-bound threads (DB writes) and asyncio (network)
- WAL mode enables concurrent SQLite readers alongside simulator writers
- Queue-based decoupling means DB latency doesn't stall simulators

### Horizontal (multi-node)
Replace PatientDataStore with Redis (pub/sub + sorted sets):
- Simulator nodes write to Redis streams
- API nodes read from Redis (no shared memory needed)
- AlertManager becomes a separate microservice consuming from Kafka topic

### Architecture evolution path
```
Phase 1 (current):  Monolith + SQLite
Phase 2:            Redis shared state + PostgreSQL
Phase 3:            Kafka event bus + microservices
Phase 4:            Kubernetes + auto-scaling per patient load
```

---

## Fault Tolerance

| Failure | Mitigation |
|---------|------------|
| Simulator thread crash | Exception caught in `run()`, thread continues |
| DB write failure | Alert logged; in-memory state preserved |
| WS client disconnect | Removed from connection pool; no impact on system |
| Full alert queue | `put_nowait` drops silently with warning log |
| DB connection stale | `pool_pre_ping=True` in SQLAlchemy engine |
| App restart | DB preserves all vitals history; simulator re-seeds from DB |
