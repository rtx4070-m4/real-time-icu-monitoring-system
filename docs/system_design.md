# System Design — Real-Time Smart ICU Monitoring System

## Problem Statement

Design a system that monitors 8–100 ICU patients in real time, detects
life-threatening vital sign anomalies, prioritises nurse attention via an
OS-inspired scheduler, and presents a live dashboard — all without data loss.

---

## Constraints & Requirements

| Constraint | Value |
|-----------|-------|
| Patients monitored | 8 (demo) → 100 (load test) |
| Vital update interval | 2 seconds |
| Alert latency | < 100 ms from generation to dashboard |
| Dashboard refresh | 2 seconds (WebSocket push) |
| Data retention | All vitals stored; last 100 in memory per patient |
| Availability | 99.9% (single node target) |

---

## Key Design Decisions

### 1. Threading vs asyncio

**Decision:** Hybrid — OS threads for simulation + asyncio for networking.

**Rationale:**
- Simulation uses `time.sleep()`-based loops → blocking → OS threads prevent
  GIL contention with the asyncio event loop.
- WebSocket broadcasting is pure I/O-bound → asyncio avoids thread-per-client.
- AlertManager uses `queue.Queue` as the bridge between thread world and
  asyncio world (producer threads, consumer thread).

### 2. Priority Queue / Heap

**Decision:** Python `heapq` (min-heap with negated priority = max-heap).

**Rationale:**
- O(log n) push/pop, O(n log n) full sort for snapshot.
- Snapshots taken every 1 s → n ≤ 100 patients → negligible cost.
- Chosen over a sorted list (O(n) insert) or priority queue from `queue`
  module (no random access for snapshot).

### 3. SQLite with WAL mode

**Decision:** SQLite (dev), PostgreSQL (prod-ready).

**Rationale:**
- WAL mode: readers never block writers. Multiple patient threads can write
  vital records while the API reads history → no lock contention.
- `pool_pre_ping=True` detects stale connections before use.
- PostgreSQL swap: just change `DATABASE_URL` env var.

### 4. Alert deduplication

**Decision:** Time-window dedup per (patient_id, vital_name) key.

**Rationale:**
- Without dedup, a patient in sustained critical SpO2 would generate an alert
  every 2 s → alert fatigue.
- 10-second window balances responsiveness (new alerts appear quickly) with
  noise reduction.

### 5. WebSocket over SSE or polling

**Decision:** WebSocket (`/ws/vitals`).

**Rationale:**
- Bidirectional: future nurse commands (e.g., acknowledge) can flow back.
- Lower overhead than HTTP polling for 2 s updates.
- SSE would be unidirectional and not supported by all reverse proxies.

---

## Data Model

```
patients
  id          INTEGER PK
  name        TEXT
  age         INTEGER
  bed_number  TEXT UNIQUE
  diagnosis   TEXT
  status      ENUM(STABLE, WATCH, CRITICAL, OFFLINE)
  created_at  DATETIME

vital_records
  id               INTEGER PK
  patient_id       INTEGER INDEX
  timestamp        DATETIME INDEX
  heart_rate       REAL
  systolic_bp      REAL
  diastolic_bp     REAL
  spo2             REAL
  temperature      REAL
  respiratory_rate REAL
  severity         ENUM(NORMAL, LOW, MEDIUM, CRITICAL)

alerts
  id           INTEGER PK
  patient_id   INTEGER INDEX
  patient_name TEXT
  bed_number   TEXT
  timestamp    DATETIME INDEX
  severity     ENUM(LOW, MEDIUM, CRITICAL)
  vital_name   TEXT
  vital_value  REAL
  message      TEXT
  acknowledged INTEGER (0/1)
```

**Indexes:** `patient_id` + `timestamp` on both `vital_records` and `alerts`
to support efficient range queries (last N records per patient).

---

## Vital Sign Simulation Model

Each vital is generated using:

```
value(t) = baseline_mean
         + sin(phase + t × 0.15) × std × 0.5    ← slow drift
         + Gaussian(0, std × 0.3)                 ← noise
```

Clamped to physiological limits. Diagnosis-specific baselines skew means
toward realistic values for each condition (e.g., Sepsis → elevated HR/Temp).

---

## API Design

RESTful, versioned under `/api/`:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/patients` | All patients |
| GET | `/api/patients/{id}` | Single patient |
| GET | `/api/vitals` | Current vitals for all |
| GET | `/api/vitals/{id}` | Patient vitals + history |
| GET | `/api/vitals/{id}/history` | Historical readings |
| GET | `/api/alerts` | Recent alerts (filterable) |
| GET | `/api/alerts/critical` | Critical alerts only |
| POST | `/api/alerts/{id}/acknowledge` | Acknowledge alert |
| GET | `/api/scheduler/queue` | Triage priority queue |
| GET | `/api/stats` | Dashboard statistics |
| WS | `/ws/vitals` | Real-time push stream |

---

## Performance Analysis

| Metric | Value |
|--------|-------|
| Threads (8 patients) | 10 (8 sim + 1 scheduler + 1 alert) |
| Memory (8 patients, 100 pts each) | ~2 MB |
| DB writes/sec | 4–8 (0.5/patient/tick) |
| WS broadcast payload | ~5 KB per update |
| Alert queue throughput | Up to 1000 pending alerts |

---

## Security Considerations (production checklist)

- [ ] Authentication: JWT via FastAPI `Depends` + OAuth2PasswordBearer
- [ ] HTTPS: TLS termination at nginx
- [ ] Rate limiting: slowapi middleware
- [ ] Input validation: Pydantic (already in place)
- [ ] Audit log: all alert acknowledgements logged with user ID
- [ ] Role-based access: nurse vs. admin vs. viewer scopes
- [ ] Secrets management: environment variables / Vault
