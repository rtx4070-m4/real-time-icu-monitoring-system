# API Documentation — ICU Monitoring System

Base URL: `http://localhost:8000`
WebSocket: `ws://localhost:8000/ws/vitals`

---

## Authentication
Currently open (dev mode). Production: add `Authorization: Bearer <token>` header.

---

## Endpoints

### Health

#### `GET /`
```json
{ "status": "operational", "system": "ICU Monitoring System", "version": "1.0.0" }
```

#### `GET /health`
```json
{ "status": "healthy", "patients_monitored": 8, "timestamp": "2024-01-15T10:30:00" }
```

---

### Patients

#### `GET /api/patients`
Returns all registered ICU patients.

**Response 200:**
```json
[
  {
    "id": 1,
    "name": "Arjun Sharma",
    "age": 67,
    "bed_number": "ICU-01",
    "diagnosis": "Acute MI",
    "status": "STABLE"
  }
]
```

#### `GET /api/patients/{patient_id}`
**Path params:** `patient_id` (integer)
**Response 404** if not found.

---

### Vitals

#### `GET /api/vitals`
Current vitals snapshot for all monitored patients.

**Response 200:**
```json
[
  {
    "patient_id": 1,
    "patient_name": "Arjun Sharma",
    "bed_number": "ICU-01",
    "status": "WATCH",
    "vitals": {
      "heart_rate": 88.3,
      "systolic_bp": 145.2,
      "diastolic_bp": 92.1,
      "spo2": 94.7,
      "temperature": 37.8,
      "respiratory_rate": 18.0,
      "severity": "LOW",
      "timestamp": "2024-01-15T10:30:02.123456"
    }
  }
]
```

#### `GET /api/vitals/{patient_id}`
Full vitals + last 20 history points.

#### `GET /api/vitals/{patient_id}/history?limit=50`
**Query params:** `limit` (1–200, default 50)

Returns array of VitalReading objects ordered oldest→newest.

---

### Alerts

#### `GET /api/alerts?limit=50&severity=CRITICAL`
**Query params:**
- `limit` (1–500, default 50)
- `severity` (NORMAL | LOW | MEDIUM | CRITICAL, optional filter)

**Response 200:**
```json
[
  {
    "id": 42,
    "patient_id": 3,
    "patient_name": "Rahul Verma",
    "bed_number": "ICU-03",
    "timestamp": "2024-01-15T10:30:05.000000",
    "severity": "CRITICAL",
    "vital_name": "SpO₂",
    "vital_value": 83.2,
    "message": "🚨 CRITICAL: SpO₂ at dangerous level: 83.2 — IMMEDIATE ATTENTION REQUIRED",
    "acknowledged": false
  }
]
```

#### `GET /api/alerts/critical`
Shorthand for severity=CRITICAL.

#### `POST /api/alerts/{alert_id}/acknowledge`
Mark alert as acknowledged.

**Response 200:**
```json
{ "acknowledged": true, "alert_id": 42 }
```

**Response 404** if alert_id not found.

---

### Scheduler / Triage

#### `GET /api/scheduler/queue`
Returns patients ranked by triage priority (highest priority = rank 1).

**Response 200:**
```json
[
  {
    "rank": 1,
    "patient_id": 4,
    "patient_name": "Sunita Gupta",
    "bed_number": "ICU-04",
    "status": "CRITICAL",
    "severity": "CRITICAL",
    "priority": 120
  },
  {
    "rank": 2,
    "patient_id": 6,
    "patient_name": "Meena Iyer",
    "bed_number": "ICU-06",
    "status": "WATCH",
    "severity": "MEDIUM",
    "priority": 35
  }
]
```

**Priority score formula:**
```
score = severity_weight + age_bonus + surge_bonus

severity_weight: NORMAL=0, LOW=10, MEDIUM=30, CRITICAL=100
age_bonus:       +2 per 5 ticks without being CRITICAL (anti-starvation)
surge_bonus:     SpO2<88 → +20, HR>150 or <40 → +15, SysBP<70 or >200 → +15
```

---

### Statistics

#### `GET /api/stats`
**Response 200:**
```json
{
  "total_patients": 8,
  "patient_status": {
    "STABLE": 5,
    "WATCH": 2,
    "CRITICAL": 1,
    "OFFLINE": 0
  },
  "total_alerts": 47,
  "critical_alerts": 3,
  "medium_alerts": 12,
  "low_alerts": 32,
  "server_time": "2024-01-15T10:30:10.000000"
}
```

---

## WebSocket

### `WS /ws/vitals`
Connect and receive live pushes every 2 seconds.

**Message format:**
```json
{
  "type": "vitals_update",
  "data": [
    {
      "patient": {
        "id": 1,
        "name": "Arjun Sharma",
        "age": 67,
        "bed_number": "ICU-01",
        "diagnosis": "Acute MI",
        "status": "STABLE"
      },
      "vitals": {
        "heart_rate": 78.2,
        "systolic_bp": 122.5,
        "diastolic_bp": 81.0,
        "spo2": 97.3,
        "temperature": 37.1,
        "respiratory_rate": 15.0,
        "severity": "NORMAL",
        "timestamp": "2024-01-15T10:30:02.000000"
      },
      "alerts": [ ...last 5 alerts for this patient... ],
      "priority": 12
    }
  ]
}
```

**JavaScript example:**
```javascript
const ws = new WebSocket("ws://localhost:8000/ws/vitals");
ws.onmessage = (event) => {
  const { type, data } = JSON.parse(event.data);
  if (type === "vitals_update") {
    data.forEach(snapshot => {
      console.log(snapshot.patient.name, snapshot.vitals.heart_rate);
    });
  }
};
```

---

## Error Responses

All errors follow FastAPI's default format:
```json
{ "detail": "Error description here" }
```

| Code | Meaning |
|------|---------|
| 400 | Bad request (invalid query param) |
| 404 | Resource not found |
| 422 | Validation error (Pydantic) |
| 500 | Internal server error |
