#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Handle graceful shutdown of background processes on script exit or interrupt
cleanup() {
  trap - SIGINT SIGTERM EXIT
  echo ""
  echo "🛑 Stopping all services..."
  kill $(jobs -p) 2>/dev/null || true
  exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# 1. Activate virtual environment if present
if [ -d "venv" ]; then
  echo "📦 Activating virtual environment..."
  source venv/bin/activate
fi

# 2. Run backend
echo "🐍 Starting backend (FastAPI) on port 8000..."
python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# 3. Run frontend
echo "⚛️ Starting frontend (React Vite) in dev mode..."
pnpm --dir frontend dev &
FRONTEND_PID=$!

# Keep the script running and wait for background processes
wait $BACKEND_PID $FRONTEND_PID
