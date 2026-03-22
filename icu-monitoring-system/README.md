# 🏥 ICU Real-Time Smart Monitoring System

> **Production-grade polyglot microservices platform for intensive care unit patient monitoring.**  
> Real-time vitals · AI-powered deterioration prediction · Event-driven alerts · WebSocket dashboard

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)](docker-compose.yml)
[![C++17](https://img.shields.io/badge/C++-17-00599C?logo=cplusplus)](core-engine/)
[![Rust](https://img.shields.io/badge/Rust-1.75-orange?logo=rust)](alert-engine/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python)](ai-module/python/)
[![Java](https://img.shields.io/badge/Java-21-ED8B00?logo=openjdk)](backend-api/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)](frontend/)

---

## 📋 Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Technology Stack](#technology-stack)
3. [Services](#services)
4. [Quick Start](#quick-start)
5. [API Reference](#api-reference)
6. [Configuration](#configuration)
7. [Testing Guide](#testing-guide)
8. [Sample Outputs](#sample-outputs)
9. [Architecture Decisions](#architecture-decisions)
10. [Contributing](#contributing)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ICU Monitoring System                        │
│                                                                     │
│  ┌──────────────┐    Kafka: icu.vitals    ┌────────────────────┐   │
│  │  C++ Core    │ ──────────────────────► │  Rust Alert Engine │   │
│  │  Engine      │                         │  (Event-Driven)    │   │
│  │  (Threads)   │                         └────────┬───────────┘   │
│  └──────┬───────┘                                  │ REST          │
│         │ Kafka: icu.vitals                        ▼               │
│         │                              ┌────────────────────┐      │
│         │◄────────────────────────────►│  Java Backend API  │      │
│         │                              │  (Spring Boot)     │      │
│  ┌──────▼───────────────────────┐     └────────┬───────────┘      │
│  │    Apache Kafka               │              │ REST/WS          │
│  │    Topics: vitals, alerts     │     ┌────────▼───────────┐      │
│  └──────────────────────────────┘     │  React Dashboard   │      │
│                                        │  (TypeScript)      │      │
│  ┌─────────────────────────────┐      └────────────────────┘      │
│  │  AI Module (3 languages)    │                                   │
│  │  Python: ML Prediction      │      ┌────────────────────┐      │
│  │  R: Statistical Analysis    │      │   PostgreSQL        │      │
│  │  Julia: Kalman Filtering    │      │   (Time-series)    │      │
│  └─────────────────────────────┘      └────────────────────┘      │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **C++ Core Engine** runs one thread per patient, simulates realistic ICU vitals using physiological models (NEWS2 scoring), and publishes JSON messages to `icu.vitals` Kafka topic at priority-based intervals (critical patients: 500ms, stable: 2000ms).

2. **Rust Alert Engine** consumes from `icu.vitals`, evaluates 15+ clinical alert rules (based on NICE/AHA guidelines), performs trend analysis for rapid deterioration detection, and POSTs alerts to the Backend API.

3. **Java Backend API** bridges all services: consumes Kafka, persists to PostgreSQL, calls AI services asynchronously, and broadcasts real-time updates via WebSocket (STOMP).

4. **AI Module** (3 polyglot services):
   - **Python**: Ensemble ML model (GBM + RF + Logistic) predicts deterioration risk (0–1)
   - **R (Plumber)**: ARIMA forecasting, changepoint detection, Mann-Kendall trend tests
   - **Julia**: Online Kalman filter for noise reduction and 5-step vital sign prediction

5. **React Dashboard** connects via WebSocket for live updates, renders per-patient vital cards with colour-coded severity, real-time Chart.js graphs, and an alert management panel.

---

## Technology Stack

| Layer              | Language / Framework    | Justification                                           |
|--------------------|-------------------------|---------------------------------------------------------|
| Core Engine        | **C++17**               | Maximum performance for real-time simulation; pthreads for concurrent patient processing |
| Alert Engine       | **Rust**                | Memory safety + zero-cost abstractions for event-driven stream processing |
| ML Prediction      | **Python 3.11**         | scikit-learn ecosystem; fastest path to production ML   |
| Statistical Analysis| **R 4.3**              | ARIMA/changepoint/Mann-Kendall: best-in-class statistical libraries |
| Kalman Filtering   | **Julia 1.10**          | Near-C performance for numerical computing; elegant syntax |
| Backend API        | **Java 21 / Spring Boot** | Enterprise-grade REST/WebSocket; best Kafka ecosystem  |
| Frontend           | **TypeScript / React 18** | Type-safe UI; excellent real-time capabilities        |
| Message Bus        | **Apache Kafka**        | Durable, partitioned, high-throughput streaming         |
| Database           | **PostgreSQL 16**       | ACID compliance; time-series via TimescaleDB-compatible |

---

## Services

| Service        | Port  | Language | Description                              |
|----------------|-------|----------|------------------------------------------|
| Frontend       | 3000  | TypeScript/React | ICU dashboard, real-time monitoring |
| Backend API    | 8080  | Java/Spring Boot | REST API + WebSocket hub              |
| AI Python      | 8082  | Python 3 | ML deterioration prediction              |
| AI R           | 8083  | R        | Statistical analysis + ARIMA forecast    |
| AI Julia       | 8084  | Julia    | Online Kalman filter                     |
| Kafka          | 29092 | —        | Message bus (external access)            |
| PostgreSQL     | 5432  | —        | Primary database                         |
| Kafka UI       | 9090  | —        | Debug UI (--debug mode)                  |
| pgAdmin        | 5050  | —        | DB admin UI (--debug mode)               |

---

## Quick Start

### Prerequisites
- Docker Engine ≥ 24.0
- Docker Compose ≥ 2.20
- 8 GB RAM recommended (6 GB minimum)
- 5 GB free disk space (image layers)

### One-Command Setup

```bash
# Clone
git clone https://github.com/your-org/icu-monitoring-system.git
cd icu-monitoring-system

# Make scripts executable
chmod +x scripts/*.sh

# Start everything (builds all images)
./scripts/setup.sh

# Start with debug tools (Kafka UI + pgAdmin)
./scripts/setup.sh --debug

# Clean rebuild (removes all volumes)
./scripts/setup.sh --clean
```

### Access Points

| URL | Description |
|-----|-------------|
| http://localhost:3000 | **ICU Dashboard** (login: admin/admin123) |
| http://localhost:8080/api/v1 | Backend REST API |
| http://localhost:8080/actuator/health | Backend health check |
| http://localhost:8082/docs | AI Python API docs |
| http://localhost:9090 | Kafka UI (debug mode) |
| http://localhost:5050 | pgAdmin (debug mode) |

---

## API Reference

### Authentication

```bash
# Login
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
# Returns: {"token": "eyJ...", "role": "ADMIN", ...}

# Use token
export TOKEN="eyJ..."
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/v1/patients
```

### Patient Endpoints

```bash
# List all active patients
GET /api/v1/patients

# Get single patient
GET /api/v1/patients/{patientId}

# Admit new patient
POST /api/v1/patients
{
  "patientId": "P009", "name": "Jane Doe", "age": 45,
  "diagnosis": "SEPSIS", "bedNumber": 9, "priority": 1
}

# Discharge patient
DELETE /api/v1/patients/{patientId}

# Vitals history (last N hours)
GET /api/v1/patients/{patientId}/vitals?hours=6

# Recent vitals
GET /api/v1/patients/{patientId}/vitals/recent?count=50

# Stats summary
GET /api/v1/patients/stats/summary
```

### Alert Endpoints

```bash
# Unacknowledged alerts
GET /api/v1/alerts

# Critical alerts only
GET /api/v1/alerts/critical

# Patient-specific alerts
GET /api/v1/alerts/patient/{patientId}?page=0&size=20

# Acknowledge an alert
PUT /api/v1/alerts/{alertId}/acknowledge
{"acknowledgedBy": "dr.smith", "notes": "Patient stabilised"}

# Alert summary stats
GET /api/v1/alerts/summary
```

### AI Module Endpoints

```bash
# Predict deterioration risk
POST http://localhost:8082/api/v1/predict
{
  "patient_id": "P001", "heart_rate": 125, "systolic_bp": 88,
  "spo2": 91, "respiratory_rate": 28, "temperature": 38.9,
  "diastolic_bp": 55, "glucose": 160, "lactate": 3.2
}
# Returns: {"deterioration_risk": 0.87, "risk_category": "IMMINENT", ...}

# Risk summary across all tracked patients
GET http://localhost:8082/api/v1/risk-summary

# Statistical analysis (R module)
POST http://localhost:8083/api/v1/forecast
{"values": [72,75,80,85,92,98], "n_ahead": 5}

# Kalman-filtered vitals (Julia module)
POST http://localhost:8084/api/v1/kalman
{"patient_id": "P001", "heart_rate": 125.5, "spo2": 91.2, ...}
```

### WebSocket Events

Connect to `ws://localhost:8080/ws` (SockJS + STOMP):

```javascript
// Subscribe topics
/topic/dashboard       → DashboardUpdate (all patients)
/topic/vitals/{id}     → VitalRecord (per patient)
/topic/alerts          → Alert (new alerts)
/topic/alerts/critical → Alert (critical/code-blue only)
/topic/patients        → Patient (admitted/discharged)
```

---

## Configuration

All services use environment variables. Key variables:

```bash
# Core Engine (C++)
KAFKA_BROKERS=kafka:9092

# Alert Engine (Rust)
KAFKA_BROKERS=kafka:9092
BACKEND_URL=http://backend-api:8080
RUST_LOG=info

# Python AI
KAFKA_BROKERS=kafka:9092
AI_API_PORT=8082

# Backend API (Java)
DB_HOST=postgres
DB_NAME=icu_db
DB_USER=icu_user
DB_PASS=icu_pass
KAFKA_BROKERS=kafka:9092
JWT_SECRET=<256-bit-secret>
AI_PYTHON_URL=http://ai-python:8082

# Frontend
REACT_APP_API_URL=http://localhost:8080
REACT_APP_WS_URL=http://localhost:8080
REACT_APP_AI_URL=http://localhost:8082
```

---

## Testing Guide

### Run API Tests

```bash
# After starting the system:
chmod +x scripts/test_api.sh
./scripts/test_api.sh
```

### Manual Test Scenarios

**Scenario 1: Code Blue Event**
```bash
# Simulate a code blue by admitting a patient with extreme vitals
# The C++ engine will automatically generate deterioration events
# Watch the dashboard for CODE BLUE alerts (purple glow)
```

**Scenario 2: Acknowledge an Alert**
```bash
TOKEN=$(curl -s -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

# Get an alert ID
ALERT_ID=$(curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/v1/alerts | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['alertId'] if d else 'none')")

# Acknowledge it
curl -X PUT "http://localhost:8080/api/v1/alerts/$ALERT_ID/acknowledge" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"acknowledgedBy": "dr.smith", "notes": "Patient stabilised after intervention"}'
```

**Scenario 3: AI Risk Prediction**
```bash
curl -X POST http://localhost:8082/api/v1/predict \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id":       "TEST",
    "heart_rate":       138,
    "systolic_bp":      82,
    "diastolic_bp":     50,
    "spo2":             88,
    "respiratory_rate": 32,
    "temperature":      39.5,
    "glucose":          220,
    "lactate":          4.8
  }'
# Expected: risk_category = "IMMINENT", deterioration_risk > 0.90
```

### Check Service Logs

```bash
docker compose logs -f core-engine      # C++ vitals simulation
docker compose logs -f alert-engine     # Rust alert events
docker compose logs -f ai-python        # ML predictions
docker compose logs -f backend-api      # API requests + WebSocket
docker compose logs -f frontend         # Nginx access log
```

### Check Kafka Messages

```bash
# Monitor vitals topic (requires kafka container running)
docker compose exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic icu.vitals \
  --from-beginning

# Monitor alerts topic
docker compose exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic icu.alerts
```

---

## Sample Outputs

### Vitals Message (Kafka → `icu.vitals`)
```json
{
  "patient_id": "P001",
  "heart_rate": 118.4,
  "systolic_bp": 91.2,
  "diastolic_bp": 58.7,
  "spo2": 92.1,
  "respiratory_rate": 26.0,
  "temperature": 38.9,
  "glucose": 187.3,
  "lactate": 3.4,
  "severity": 2,
  "timestamp": "2025-03-22T14:35:42Z"
}
```

### Alert Event (Rust Engine)
```json
{
  "alert_id": "a3f7d92e-1b4c-4f8a-9e2d-5c6b7a8f9012",
  "patient_id": "P001",
  "alert_type": "SEPSIS_ALERT",
  "severity": "CRITICAL",
  "message": "Possible sepsis: qSOFA-like score 4 – initiate sepsis bundle",
  "triggered_at": "2025-03-22T14:35:42Z"
}
```

### AI Prediction (Python)
```json
{
  "patient_id": "P001",
  "deterioration_risk": 0.8734,
  "risk_category": "IMMINENT",
  "predicted_event_hours": 0.5,
  "confidence": 0.8734,
  "feature_importances": {
    "lactate": 0.187,
    "spo2": 0.163,
    "news2_score": 0.141,
    "shock_index": 0.112,
    "systolic_bp": 0.098
  }
}
```

### Kalman Filter Output (Julia)
```json
{
  "patient_id": "P001",
  "smoothed": {
    "heart_rate": 116.8,
    "systolic_bp": 92.1,
    "spo2": 92.3,
    "respiratory_rate": 25.7,
    "temperature": 38.91,
    "lactate": 3.38
  },
  "predictions": {
    "spo2": {
      "values": [92.2, 92.1, 91.9, 91.7, 91.5],
      "uncertainty": [0.52, 0.58, 0.63, 0.68, 0.72]
    }
  }
}
```

---

## Architecture Decisions

### Why Each Language Was Chosen

**C++ for the Core Engine** – The patient simulator needs to run 8+ patients as concurrent threads with sub-second update cycles. C++ provides the scheduling precision, thread control, and raw performance required. The priority queue (`std::priority_queue`) maps naturally to ICU triage.

**Rust for Alert Processing** – Alert detection must be reliable (no crashes, no data races), low-latency, and memory-efficient. Rust's ownership model guarantees these properties at compile time. The `tokio` async runtime handles the Kafka stream efficiently without blocking.

**Python for ML** – scikit-learn's GradientBoostingClassifier, RandomForestClassifier, and cross-validation tooling are the fastest path to a production-quality deterioration model. Python's data ecosystem (numpy, pandas) is unmatched for feature engineering.

**R for Statistics** – ARIMA forecasting (`forecast`), Mann-Kendall trend tests, PELT changepoint detection (`changepoint`) – these algorithms are best implemented and maintained in R's clinical statistics ecosystem. `Plumber` provides a clean REST interface.

**Julia for Kalman Filtering** – Kalman filter mathematics involves dense matrix operations where Julia's JIT compiler matches C performance while remaining readable. The `HTTP.jl` stack handles concurrent requests efficiently.

**Java/Spring Boot for the Backend** – Enterprise-grade: Spring Kafka, Spring Security (JWT), Spring WebSocket (STOMP), Spring Data JPA. Best ecosystem for the "connection hub" role that requires integrating multiple protocols.

**TypeScript/React for Frontend** – Type safety catches vital-display bugs at compile time. React's state model handles real-time WebSocket streams well. Chart.js integrates smoothly for time-series visualisation.

### Why Kafka (not RabbitMQ)

- **Durable replay**: Vitals can be replayed for incident analysis
- **Consumer groups**: Python AI, Backend API, and Alert Engine independently consume the same stream
- **Partitioning**: Patient data can be partitioned by `patient_id` for ordered processing
- **Throughput**: At 8 patients × 2 updates/sec = 16 msg/s – Kafka is overkill for the demo but production-ready for 100s of patients

---

## Security Notes

⚠️ **For production deployment:**
- Change all default passwords in `docker-compose.yml`
- Generate a 256-bit random JWT secret: `openssl rand -base64 32`
- Enable TLS on all services
- Restrict CORS to specific frontend origin
- Enable Kafka SSL/SASL authentication
- Use PostgreSQL connection pooling (PgBouncer) under load
- Store secrets in HashiCorp Vault or AWS Secrets Manager

---

## License

MIT License – see [LICENSE](LICENSE)

---

*Built with ❤️ for critical care engineering*
