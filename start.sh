#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# start.sh — Launch the Nifty Signal Analyzer (backend + frontend)
# Usage:  ./start.sh
#         ./start.sh --install   (also installs/updates dependencies first)
# ─────────────────────────────────────────────────────────────────────────────

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Colour

log()  { echo -e "${GREEN}[start]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC}  $*"; }
err()  { echo -e "${RED}[error]${NC} $*"; }

# ── Trap: kill both child processes on Ctrl-C, SIGTERM, or any exit ───────────
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo ""
  log "Shutting down..."
  [ -n "$BACKEND_PID" ]  && kill "$BACKEND_PID"  2>/dev/null || true
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null || true
  # Wait briefly for processes to die cleanly
  [ -n "$BACKEND_PID" ]  && wait "$BACKEND_PID"  2>/dev/null || true
  [ -n "$FRONTEND_PID" ] && wait "$FRONTEND_PID" 2>/dev/null || true
  log "All processes stopped."
}
# Catch Ctrl-C, SIGTERM, and normal script exit so cleanup always runs
trap cleanup SIGINT SIGTERM EXIT

# ── Optional dependency install ───────────────────────────────────────────────
if [[ "$1" == "--install" ]]; then
  log "Installing Python dependencies..."
  pip3 install -r "$BACKEND_DIR/requirements.txt" --break-system-packages -q
  log "Installing Node dependencies..."
  cd "$FRONTEND_DIR" && npm install --silent
  cd "$ROOT_DIR"
fi

# ── Check prerequisites ───────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  err "python3 not found. Install Python 3.10+ and try again."
  exit 1
fi

if ! command -v node &>/dev/null; then
  err "node not found. Install Node.js 18+ and try again."
  exit 1
fi

if ! python3 -c "import fastapi" &>/dev/null; then
  warn "Python dependencies not installed. Run:  ./start.sh --install"
  warn "Attempting install now..."
  pip3 install -r "$BACKEND_DIR/requirements.txt" --break-system-packages -q
fi

# Verify critical backend dependencies are present
for pkg in sklearn scipy pytz; do
  if ! python3 -c "import $pkg" &>/dev/null; then
    warn "Missing Python package: $pkg — running pip install..."
    pip3 install -r "$BACKEND_DIR/requirements.txt" --break-system-packages -q
    break
  fi
done

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  warn "Node modules not found. Installing..."
  cd "$FRONTEND_DIR" && npm install --silent && cd "$ROOT_DIR"
fi

# ── Clean up any existing processes on ports 3000 and 8000 ───────────────────
log "Checking for existing processes on ports 3000 and 8000..."
if command -v fuser &>/dev/null; then
  fuser -k 3000/tcp 8000/tcp 2>/dev/null || true
  log "Cleaned up existing processes ✓"
else
  # fuser not available — try lsof + kill as fallback
  for port in 3000 8000; do
    pid=$(lsof -ti ":$port" 2>/dev/null) && [ -n "$pid" ] && kill -9 $pid 2>/dev/null || true
  done
  warn "fuser not available, used lsof fallback for port cleanup"
fi

# Give the OS a moment to release the ports
sleep 1

# ── Start backend ─────────────────────────────────────────────────────────────
log "Starting FastAPI backend on http://localhost:8000 ..."
cd "$BACKEND_DIR"
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd "$ROOT_DIR"

# Give the backend a moment to bind
sleep 3

# Quick health check
if curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
  log "Backend is up ✓"
else
  warn "Backend health check failed — it may still be starting up (CAS model warm-start can take ~10s)"
fi

# ── Start frontend ────────────────────────────────────────────────────────────
log "Starting React frontend on http://localhost:3000 ..."
cd "$FRONTEND_DIR"
# BROWSER=none: don't auto-open a browser tab
# WDS_SOCKET_PORT=3000: fixes the webpack-dev-server HMR WebSocket URL when
#   running via a script (otherwise it tries to connect to the wrong port).
#   NOTE: HMR is disabled in this project (hot:false, liveReload:true) due to
#   a webpack5 + webpack-dev-server compatibility issue — full-page reload on
#   save still works. See .clinerules for details.
BROWSER=none WDS_SOCKET_PORT=3000 npm start &
FRONTEND_PID=$!
cd "$ROOT_DIR"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  Nifty Signal Analyzer${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  Frontend  →  ${GREEN}http://localhost:3000${NC}"
echo -e "  Backend   →  ${GREEN}http://localhost:8000${NC}"
echo -e "  API docs  →  ${GREEN}http://localhost:8000/docs${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  Press ${YELLOW}Ctrl-C${NC} to stop both servers"
echo ""

# ── Wait for both processes ───────────────────────────────────────────────────
# Disable set -e for the wait so a crashed process doesn't skip cleanup
set +e
wait $BACKEND_PID $FRONTEND_PID