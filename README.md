# 🏥 Real-Time Smart ICU Monitoring System

> **FAANG-Level** distributed real-time system demonstrating OS concepts,
> multithreading, priority scheduling, and event-driven architecture.

---

## 🚀 Quick Start (3 commands)

```bash
# 1. Install dependencies
cd backend && pip install -r requirements.txt

# 2. Start backend
python main.py

# 3. Open frontend  (new terminal)
open ../frontend/index.html      # macOS
xdg-open ../frontend/index.html  # Linux
# Or just double-click frontend/index.html
```

Backend API:  http://localhost:8000
API Docs:     http://localhost:8000/docs
Frontend:     file:///path/to/frontend/index.html

---

## 🐳 Docker (recommended)

```bash
cd docker
docker compose up --build

# Frontend: http://localhost:3000
# API:      http://localhost:8000
# Docs:     http://localhost:8000/docs
```

For PostgreSQL production mode:
```bash
docker compose --profile prod up --build
```

---

## 🧪 Run Tests

```bash
cd backend

# Scheduler unit tests (fast, no server needed)
pytest ../tests/test_scheduler.py -v

# API integration tests (starts app internally)
pytest ../tests/test_api.py -v --asyncio-mode=auto

# All tests
pytest ../tests/ -v --asyncio-mode=auto
```

---

## 📂 Project Structure

```
icu-monitoring-system/
│
├── backend/
│   ├── main.py          ← FastAPI app + WebSocket broadcaster
│   ├── simulator.py     ← Multithreaded patient vital simulator
│   ├── scheduler.py     ← OS-inspired priority scheduler
│   ├── alerts.py        ← Thread-safe alert manager
│   ├── models.py        ← SQLAlchemy ORM + Pydantic schemas
│   ├── database.py      ← DB engine, sessions, seed data
│   ├── config.py        ← Centralized configuration
│   └── requirements.txt
│
├── frontend/
│   ├── index.html       ← Dashboard layout
│   ├── app.js           ← WebSocket client + Chart.js
│   └── styles.css       ← Dark ICU aesthetic
│
├── docker/
│   ├── Dockerfile       ← Multi-stage production build
│   ├── docker-compose.yml
│   └── nginx.conf
│
├── tests/
│   ├── test_scheduler.py ← 15 unit tests
│   └── test_api.py       ← 14 integration tests
│
├── docs/
│   ├── architecture.md  ← System architecture + diagrams
│   ├── system_design.md ← Design decisions + trade-offs
│   └── api_docs.md      ← Full API reference
│
├── README.md
└── run.sh               ← One-command startup script
```

---

## ⚙️ Configuration

All settings configurable via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./icu.db` | DB connection string |
| `SIM_INTERVAL` | `2.0` | Seconds between vital readings |
| `PATIENT_COUNT` | `8` | Number of simulated patients |
| `MAX_HISTORY` | `100` | In-memory history points per patient |
| `API_HOST` | `0.0.0.0` | Server bind address |
| `API_PORT` | `8000` | Server port |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `SCHEDULER_TICK` | `1.0` | Scheduler recalculation interval |
| `WS_INTERVAL` | `2.0` | WebSocket broadcast interval |
| `MAX_ALERTS` | `500` | In-memory alert ring buffer size |

---

## 🧠 Core Concepts Demonstrated

### Operating Systems
| Concept | Implementation |
|---------|---------------|
| **Multithreading** | `threading.Thread` per patient (OS-managed) |
| **Mutex / RLock** | `threading.RLock` on `PatientDataStore` |
| **Semaphore** | `queue.Queue(maxsize=1000)` in AlertManager |
| **Condition Variables** | `threading.Condition` for CRITICAL event notification |
| **Producer-Consumer** | Simulator threads → `queue.Queue` → AlertManager |
| **Priority Scheduling** | ICUScheduler with max-heap + aging |
| **Preemption Detection** | Logged when queue top changes |

### Distributed Systems
| Concept | Implementation |
|---------|---------------|
| **Event-driven** | WS broadcaster, callback chains |
| **Deduplication** | Time-window dedup in AlertManager |
| **Back-pressure** | `put_nowait` drops on full queue with warning |
| **Fault tolerance** | Try/catch in all thread loops, pool_pre_ping |
| **Config-driven** | All settings via env vars (12-factor) |

### Real-Time Processing
| Concept | Implementation |
|---------|---------------|
| **Streaming** | WebSocket push every 2 s |
| **Ring buffer** | `deque(maxlen=N)` for history + alerts |
| **Time-series** | Chart.js sliding window (30 points) |
| **Low-latency alerts** | < 100 ms from generation to dashboard |

---

## 🔌 API Highlights

```bash
# All patient vitals
curl http://localhost:8000/api/vitals

# Priority triage queue
curl http://localhost:8000/api/scheduler/queue

# Critical alerts only
curl http://localhost:8000/api/alerts?severity=CRITICAL

# System stats
curl http://localhost:8000/api/stats

# Interactive docs
open http://localhost:8000/docs
```

---

## 📊 Dashboard Features

- **Live patient cards** — update every 2 s via WebSocket
- **Color-coded severity** — green (stable) → amber (watch) → red (critical)
- **Pulsing animation** — critical patients visually pulse
- **Triage queue** — priority-ordered patient list (top = most urgent)
- **Vital trend chart** — click any patient to see HR / SpO₂ / BP over time
- **Alert feed** — real-time stream with severity icons
- **Sort modes** — sort by priority, name, or bed number

---

## 🏗️ Extending the System

### Add more patients
```python
# database.py → SEED_PATIENTS list
{"name": "New Patient", "age": 55, "bed_number": "ICU-09", "diagnosis": "Heart Failure"}
```

### Add ML anomaly detection
```python
# simulator.py → _generate_reading()
from sklearn.ensemble import IsolationForest
# Train on historical data, score each reading
```

### Switch to PostgreSQL
```bash
export DATABASE_URL="postgresql://user:pass@localhost/icu"
python main.py
```

### Scale to 100 patients
```bash
export PATIENT_COUNT=100
export SIM_INTERVAL=1.0
python main.py
```

---

## 🧩 Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, uvicorn |
| Database | SQLAlchemy 2.0, SQLite / PostgreSQL |
| Real-time | WebSockets (native FastAPI) |
| Threading | Python `threading` module (OS threads) |
| Frontend | Vanilla JS, Chart.js 4, CSS custom properties |
| Container | Docker multi-stage, nginx |
| Testing | pytest, pytest-asyncio, httpx |

---

## 📄 License

MIT — built for educational and portfolio purposes.
