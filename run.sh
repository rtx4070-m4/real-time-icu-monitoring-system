#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
#  run.sh — One-command startup for ICU Monitoring System
#  Usage:
#    ./run.sh          → starts backend + opens frontend
#    ./run.sh --docker → starts via Docker Compose
#    ./run.sh --test   → runs test suite
# ══════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
DOCKER_DIR="$SCRIPT_DIR/docker"

# ── Colors ────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

log()  { echo -e "${CYAN}[ICU]${RESET} $*"; }
ok()   { echo -e "${GREEN}[✓]${RESET} $*"; }
warn() { echo -e "${YELLOW}[!]${RESET} $*"; }
err()  { echo -e "${RED}[✗]${RESET} $*"; exit 1; }

banner() {
  echo -e "${BOLD}${CYAN}"
  echo "  ██╗ ██████╗██╗   ██╗"
  echo "  ██║██╔════╝██║   ██║"
  echo "  ██║██║     ██║   ██║"
  echo "  ██║██║     ██║   ██║"
  echo "  ██║╚██████╗╚██████╔╝"
  echo "  ╚═╝ ╚═════╝ ╚═════╝ "
  echo -e "${RESET}${BOLD}  Real-Time Smart ICU Monitoring System${RESET}"
  echo ""
}

# ── Docker mode ───────────────────────────────────────────────────
if [[ "${1:-}" == "--docker" ]]; then
  banner
  log "Starting via Docker Compose…"
  cd "$DOCKER_DIR"
  docker compose up --build
  exit 0
fi

# ── Test mode ─────────────────────────────────────────────────────
if [[ "${1:-}" == "--test" ]]; then
  banner
  log "Running test suite…"
  cd "$BACKEND_DIR"
  python -m pytest ../tests/ -v --asyncio-mode=auto --tb=short
  exit 0
fi

# ── Normal mode ───────────────────────────────────────────────────
banner

# Check Python
command -v python3 &>/dev/null || err "Python 3 not found. Install Python 3.10+"
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
log "Python version: $PY_VER"

# Install deps
log "Installing Python dependencies…"
cd "$BACKEND_DIR"
pip install -q -r requirements.txt
ok "Dependencies installed."

# Start backend in background
log "Starting ICU backend on http://localhost:8000 …"
python3 main.py &
BACKEND_PID=$!

# Wait for backend to be ready
log "Waiting for backend to initialise…"
for i in {1..20}; do
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    ok "Backend is up! (PID: $BACKEND_PID)"
    break
  fi
  sleep 0.5
  if [[ $i -eq 20 ]]; then
    err "Backend failed to start. Check logs above."
  fi
done

# Open frontend
FRONTEND_URL="file://$FRONTEND_DIR/index.html"
log "Opening dashboard: $FRONTEND_URL"
case "$(uname -s)" in
  Darwin*)  open "$FRONTEND_URL" ;;
  Linux*)   xdg-open "$FRONTEND_URL" 2>/dev/null || warn "Open manually: $FRONTEND_URL" ;;
  CYGWIN*|MINGW*) start "$FRONTEND_URL" ;;
  *) warn "Open manually: $FRONTEND_URL" ;;
esac

echo ""
echo -e "${BOLD}═══════════════════════════════════════════${RESET}"
echo -e "  ${GREEN}System running!${RESET}"
echo -e "  Backend API:  ${CYAN}http://localhost:8000${RESET}"
echo -e "  Swagger Docs: ${CYAN}http://localhost:8000/docs${RESET}"
echo -e "  Dashboard:    ${CYAN}$FRONTEND_URL${RESET}"
echo -e "${BOLD}═══════════════════════════════════════════${RESET}"
echo ""
echo -e "  Press ${BOLD}Ctrl+C${RESET} to stop."
echo ""

# Wait for Ctrl+C
trap "kill $BACKEND_PID 2>/dev/null; echo ''; log 'System stopped.'" INT TERM
wait $BACKEND_PID
