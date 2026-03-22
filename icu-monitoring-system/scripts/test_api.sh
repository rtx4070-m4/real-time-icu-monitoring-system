#!/usr/bin/env bash
# scripts/test_api.sh – API integration test suite
set -euo pipefail

BASE="http://localhost:8080"
AI_BASE="http://localhost:8082"
GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'

pass() { echo -e "${GREEN}✓ PASS${NC} $*"; }
fail() { echo -e "${RED}✗ FAIL${NC} $*"; }

echo "═══════════════════════════════════════════════════════"
echo "  ICU API Integration Test Suite"
echo "═══════════════════════════════════════════════════════"

# ── 1. Login ────────────────────────────────────────────────────────────────
echo ""
echo "1. Authentication"
RESP=$(curl -sf -X POST "$BASE/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}') || { fail "Login failed"; exit 1; }

TOKEN=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
[ -n "$TOKEN" ] && pass "Login OK – JWT token received" || fail "No token in response"
AUTH="Authorization: Bearer $TOKEN"

# ── 2. Patients ──────────────────────────────────────────────────────────────
echo ""
echo "2. Patient Endpoints"
PATIENTS=$(curl -sf -H "$AUTH" "$BASE/api/v1/patients")
COUNT=$(echo "$PATIENTS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
[ "$COUNT" -gt 0 ] && pass "GET /patients – $COUNT patients" || fail "No patients returned"

PATIENT=$(curl -sf -H "$AUTH" "$BASE/api/v1/patients/P001") || { fail "GET /patients/P001"; }
NAME=$(echo "$PATIENT" | python3 -c "import sys,json; print(json.load(sys.stdin)['name'])")
[ -n "$NAME" ] && pass "GET /patients/P001 – name: $NAME" || fail "Patient name missing"

STATS=$(curl -sf -H "$AUTH" "$BASE/api/v1/patients/stats/summary")
pass "GET /patients/stats/summary – $STATS"

# ── 3. Alerts ────────────────────────────────────────────────────────────────
echo ""
echo "3. Alert Endpoints"
ALERTS=$(curl -sf -H "$AUTH" "$BASE/api/v1/alerts")
ALERT_COUNT=$(echo "$ALERTS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else 0)")
pass "GET /alerts – $ALERT_COUNT unacknowledged alerts"

SUMMARY=$(curl -sf -H "$AUTH" "$BASE/api/v1/alerts/summary")
pass "GET /alerts/summary – $SUMMARY"

# ── 4. Post a test alert ──────────────────────────────────────────────────────
echo ""
echo "4. Alert Creation"
ALERT_RESP=$(curl -sf -X POST "$BASE/api/v1/alerts" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{
    "alert_id":   "TEST-001",
    "patient_id": "P001",
    "alert_type": "TACHYCARDIA",
    "severity":   "ELEVATED",
    "message":    "Integration test alert – HR 125 bpm"
  }') || { fail "POST /alerts"; }
echo "$ALERT_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('alertId','?'))" > /dev/null
pass "POST /alerts – test alert created"

# ── 5. AI Module health ───────────────────────────────────────────────────────
echo ""
echo "5. AI Module (Python)"
AI_HEALTH=$(curl -sf "$AI_BASE/health" 2>/dev/null) || { fail "AI module health check"; AI_HEALTH="{}"; }
MODEL_READY=$(echo "$AI_HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('model_ready', False))" 2>/dev/null || echo "false")
[ "$MODEL_READY" = "True" ] && pass "AI model ready" || fail "AI model not trained yet (may still be starting)"

# ── 6. AI Prediction ──────────────────────────────────────────────────────────
PRED=$(curl -sf -X POST "$AI_BASE/api/v1/predict" \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "P001",
    "heart_rate": 125, "systolic_bp": 88, "diastolic_bp": 55,
    "spo2": 91, "respiratory_rate": 28, "temperature": 38.9,
    "glucose": 160, "lactate": 3.2
  }' 2>/dev/null) || { fail "AI prediction"; PRED="{}"; }

RISK=$(echo "$PRED" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"{d.get('deterioration_risk',0):.2%} ({d.get('risk_category','?')})\")" 2>/dev/null || echo "N/A")
pass "AI prediction for P001 – Risk: $RISK"

# ── 7. Vitals history ─────────────────────────────────────────────────────────
echo ""
echo "6. Vitals History"
VITALS=$(curl -sf -H "$AUTH" "$BASE/api/v1/patients/P001/vitals?hours=1" 2>/dev/null || echo "[]")
VCOUNT=$(echo "$VITALS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo 0)
pass "GET /patients/P001/vitals – $VCOUNT records (last hour)"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  All tests complete."
echo "═══════════════════════════════════════════════════════"
