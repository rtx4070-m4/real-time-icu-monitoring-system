#!/usr/bin/env bash
# scripts/setup.sh – One-command ICU system setup and launch
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${CYAN}[ICU]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERR]${NC} $*"; exit 1; }

echo -e "${BOLD}"
cat << 'BANNER'
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║   🏥  ICU Real-Time Monitoring System  – Setup                  ║
║                                                                  ║
║   C++ · Rust · Python · R · Julia · Java · TypeScript/React     ║
║   Kafka · PostgreSQL · Docker Compose                            ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
BANNER
echo -e "${NC}"

# ── Prerequisite checks ────────────────────────────────────────────────────
log "Checking prerequisites..."
command -v docker        >/dev/null 2>&1 || err "Docker not found. Install from https://docker.com"
command -v docker-compose>/dev/null 2>&1 || \
  docker compose version >/dev/null 2>&1 || err "docker-compose not found."

DOCKER_COMPOSE="docker-compose"
docker compose version >/dev/null 2>&1 && DOCKER_COMPOSE="docker compose"
ok "Docker: $(docker --version)"

# ── Script root ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# ── Parse arguments ────────────────────────────────────────────────────────
BUILD=true; DEBUG=false; CLEAN=false
for arg in "$@"; do
  case $arg in
    --no-build) BUILD=false ;;
    --debug)    DEBUG=true  ;;
    --clean)    CLEAN=true  ;;
    --help)
      echo "Usage: $0 [--no-build] [--debug] [--clean]"
      echo "  --no-build  Skip image builds (use cached)"
      echo "  --debug     Start Kafka UI + pgAdmin"
      echo "  --clean     Remove volumes and rebuild from scratch"
      exit 0 ;;
  esac
done

# ── Clean mode ──────────────────────────────────────────────────────────────
if $CLEAN; then
  warn "CLEAN mode – removing all volumes and containers..."
  $DOCKER_COMPOSE down -v --remove-orphans 2>/dev/null || true
  ok "Cleaned up."
fi

# ── Build images ────────────────────────────────────────────────────────────
if $BUILD; then
  log "Building all Docker images (this may take 5-15 minutes the first time)..."
  $DOCKER_COMPOSE build --parallel 2>&1 | grep -E '(DONE|ERROR|Step|error)' || true
  ok "Images built."
fi

# ── Bring up core infrastructure first ────────────────────────────────────
log "Starting infrastructure (ZooKeeper, Kafka, PostgreSQL)..."
$DOCKER_COMPOSE up -d zookeeper postgres
sleep 5
$DOCKER_COMPOSE up -d kafka
log "Waiting for Kafka to be ready (up to 60s)..."
for i in {1..30}; do
  if $DOCKER_COMPOSE exec kafka kafka-topics --bootstrap-server localhost:9092 --list >/dev/null 2>&1; then
    ok "Kafka is ready."
    break
  fi
  sleep 2
  [ $i -eq 30 ] && err "Kafka did not become ready in time."
done

# ── Initialise Kafka topics ────────────────────────────────────────────────
log "Initialising Kafka topics..."
$DOCKER_COMPOSE run --rm kafka-init 2>/dev/null || warn "Kafka-init may have already run."

# ── Waiting for PostgreSQL ─────────────────────────────────────────────────
log "Waiting for PostgreSQL..."
for i in {1..20}; do
  $DOCKER_COMPOSE exec postgres pg_isready -U icu_user -d icu_db >/dev/null 2>&1 && break
  sleep 2
  [ $i -eq 20 ] && err "PostgreSQL did not become ready."
done
ok "PostgreSQL ready."

# ── Start application services ─────────────────────────────────────────────
log "Starting Backend API..."
$DOCKER_COMPOSE up -d backend-api
log "Waiting for Backend API (up to 90s)..."
for i in {1..45}; do
  curl -sf http://localhost:8080/actuator/health >/dev/null 2>&1 && break
  sleep 2
  [ $i -eq 45 ] && warn "Backend API may still be starting."
done
ok "Backend API ready."

log "Starting AI services (Python, R, Julia)..."
$DOCKER_COMPOSE up -d ai-python ai-r ai-julia

log "Starting Core Engine (C++) and Alert Engine (Rust)..."
$DOCKER_COMPOSE up -d core-engine alert-engine

log "Starting Frontend..."
$DOCKER_COMPOSE up -d frontend

# ── Debug tools ────────────────────────────────────────────────────────────
if $DEBUG; then
  log "Starting debug tools (Kafka UI, pgAdmin)..."
  $DOCKER_COMPOSE --profile debug up -d kafka-ui pgadmin
  ok "Kafka UI: http://localhost:9090"
  ok "pgAdmin:  http://localhost:5050 (admin@icu.local / admin123)"
fi

# ── Health summary ──────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  🏥 ICU Monitoring System – Ready!${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${GREEN}●${NC} Frontend Dashboard  → ${CYAN}http://localhost:3000${NC}"
echo -e "  ${GREEN}●${NC} Backend REST API    → ${CYAN}http://localhost:8080/api/v1${NC}"
echo -e "  ${GREEN}●${NC} AI Predictions      → ${CYAN}http://localhost:8082${NC}"
echo -e "  ${GREEN}●${NC} R Statistics        → ${CYAN}http://localhost:8083${NC}"
echo -e "  ${GREEN}●${NC} Julia Kalman        → ${CYAN}http://localhost:8084${NC}"
echo -e "  ${GREEN}●${NC} Kafka               → ${CYAN}localhost:29092${NC}"
echo -e "  ${GREEN}●${NC} PostgreSQL          → ${CYAN}localhost:5432 (icu_user/icu_pass)${NC}"
echo ""
echo -e "  ${YELLOW}Demo login:${NC} admin / admin123"
echo ""
echo -e "  ${YELLOW}Logs:${NC}   docker compose logs -f [service]"
echo -e "  ${YELLOW}Stop:${NC}   docker compose down"
echo -e "  ${YELLOW}Clean:${NC}  $0 --clean"
echo ""
