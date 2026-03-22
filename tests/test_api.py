"""
tests/test_api.py — Integration tests for the FastAPI REST endpoints.

Uses httpx.AsyncClient against a real in-process app (no external server).
Run with: cd backend && pytest ../tests/test_api.py -v --asyncio-mode=auto
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Patch database URL to use in-memory SQLite for tests
os.environ["DATABASE_URL"] = "sqlite://"

from main import app


# ─── Helpers ─────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client():
    """Async test client wrapping the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ─── Health / root ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_root(client):
    r = await client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "operational"


@pytest.mark.asyncio
async def test_health_endpoint(client):
    r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data
    assert data["status"] == "healthy"
    assert "patients_monitored" in data


# ─── Patients ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_patients(client):
    r = await client.get("/api/patients")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    # Seed patients should exist
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_get_patient_by_id(client):
    # First get list to find a valid id
    r = await client.get("/api/patients")
    patients = r.json()
    pid = patients[0]["id"]

    r2 = await client.get(f"/api/patients/{pid}")
    assert r2.status_code == 200
    p = r2.json()
    assert p["id"] == pid
    assert "name" in p
    assert "bed_number" in p


@pytest.mark.asyncio
async def test_get_patient_not_found(client):
    r = await client.get("/api/patients/99999")
    assert r.status_code == 404


# ─── Vitals ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_all_vitals(client):
    # Give the simulator a moment to produce first readings
    await asyncio.sleep(3)
    r = await client.get("/api/vitals")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_get_vitals_history(client):
    await asyncio.sleep(3)
    r = await client.get("/api/patients")
    patients = r.json()
    pid = patients[0]["id"]

    r2 = await client.get(f"/api/vitals/{pid}/history?limit=10")
    assert r2.status_code in (200, 404)   # 404 if no data yet


# ─── Alerts ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_alerts(client):
    r = await client.get("/api/alerts")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_get_critical_alerts(client):
    r = await client.get("/api/alerts/critical")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    for a in data:
        assert a["severity"] == "CRITICAL"


@pytest.mark.asyncio
async def test_get_alerts_filtered_severity(client):
    r = await client.get("/api/alerts?severity=CRITICAL")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_get_alerts_invalid_severity(client):
    r = await client.get("/api/alerts?severity=BANANA")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_acknowledge_missing_alert(client):
    r = await client.post("/api/alerts/99999/acknowledge")
    assert r.status_code == 404


# ─── Scheduler ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_priority_queue(client):
    await asyncio.sleep(2)
    r = await client.get("/api/scheduler/queue")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)

    # Verify ordering: rank should be monotonically increasing
    for i, entry in enumerate(data):
        assert entry["rank"] == i + 1

    # Priority should be descending
    priorities = [e["priority"] for e in data]
    assert priorities == sorted(priorities, reverse=True), \
        "Priority queue should be sorted highest-first"


# ─── Stats ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stats(client):
    r = await client.get("/api/stats")
    assert r.status_code == 200
    data = r.json()
    assert "total_patients" in data
    assert "patient_status" in data
    assert "total_alerts" in data
    assert data["total_patients"] >= 0


# ─── Response shape validation ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_vitals_shape(client):
    await asyncio.sleep(3)
    r = await client.get("/api/vitals")
    data = r.json()
    if data:
        v = data[0]
        assert "patient_id" in v
        assert "patient_name" in v
        assert "vitals" in v
        vitals = v["vitals"]
        for field in ("heart_rate", "spo2", "systolic_bp", "diastolic_bp",
                      "temperature", "respiratory_rate", "severity"):
            assert field in vitals, f"Missing field: {field}"
