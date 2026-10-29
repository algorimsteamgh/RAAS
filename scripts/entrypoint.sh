#!/bin/bash
set -eo pipefail

echo "🚀 Starting CV Screening Application Services..."

# Paths for SQLite persistence
PERSISTENT_DIR="${PERSISTENT_DATA_DIR:-/app/data}"
PERSISTENT_DB="${PERSISTENT_DIR}/cv_screening.db"
LOCAL_DB="${DATABASE_PATH:-/app/local_data/cv_screening.db}"
LOCAL_DIR=$(dirname "$LOCAL_DB")
LAST_BACKUP_TIMESTAMP_FILE="${LOCAL_DIR}/.last_successful_backup"

mkdir -p "$LOCAL_DIR" "$PERSISTENT_DIR"

# ------------------------------------------------------------------------------
# 1. Safe Startup Restoration & Validation
# ------------------------------------------------------------------------------
if [ -f "$PERSISTENT_DB" ]; then
    echo "🔍 Found persistent database snapshot at ${PERSISTENT_DB}."
    
    # Validate persistent DB integrity before restoring
    INTEGRITY_CHECK=$(python3 -c "
import sqlite3, sys
try:
    conn = sqlite3.connect('${PERSISTENT_DB}')
    res = conn.execute('PRAGMA integrity_check;').fetchone()
    conn.close()
    if res and res[0] == 'ok':
        sys.exit(0)
    else:
        sys.exit(1)
except Exception:
    sys.exit(1)
" 2>/dev/null && echo "ok" || echo "failed")

    if [ "$INTEGRITY_CHECK" = "ok" ]; then
        if [ ! -f "$LOCAL_DB" ] || [ "$PERSISTENT_DB" -nt "$LOCAL_DB" ]; then
            echo "📦 Restoring verified snapshot to working database: ${LOCAL_DB}..."
            python3 -c "
import shutil, sys
try:
    shutil.copyfile('${PERSISTENT_DB}', '${LOCAL_DB}')
    sys.exit(0)
except Exception as e:
    sys.stderr.write(f'Restoration error: {e}\n')
    sys.exit(1)
"
            echo "✅ Database restored successfully."
            touch "$LAST_BACKUP_TIMESTAMP_FILE"
        else
            echo "ℹ️ Working database ${LOCAL_DB} is already up to date. Skipping restore."
        fi
    else
        # CORRECTION 2: Do NOT silently ignore corruption or overwrite with fresh DB
        QUARANTINE_BACKUP="${PERSISTENT_DIR}/cv_screening_corrupted_$(date +%s).db"
        echo "❌ CRITICAL ERROR: Persistent database snapshot at ${PERSISTENT_DB} failed integrity check!"
        echo "🚨 Quarantining corrupted file to ${QUARANTINE_BACKUP} for investigation..."
        mv "$PERSISTENT_DB" "$QUARANTINE_BACKUP"
        echo "🛑 Terminating container startup to prevent silent loss of recoverable data."
        echo "   Please inspect the quarantined database file before resuming."
        exit 1
    fi
else
    echo "ℹ️ No previous persistent snapshot found at ${PERSISTENT_DB}. Backend will initialize fresh seed dataset."
fi

# ------------------------------------------------------------------------------
# 2. Online Backup Helper Function (Uses Python SQLite Online Backup API)
# ------------------------------------------------------------------------------
perform_online_backup() {
    local is_shutdown="${1:-false}"
    if [ ! -f "$LOCAL_DB" ]; then
        return 0
    fi

    # CORRECTION 1: Return explicit exit codes, log errors, track backup age
    python3 -c "
import sqlite3, os, sys, tempfile, time, shutil

local_path = '${LOCAL_DB}'
persist_path = '${PERSISTENT_DB}'
persist_dir = '${PERSISTENT_DIR}'
timestamp_file = '${LAST_BACKUP_TIMESTAMP_FILE}'
local_dir = os.path.dirname(local_path)

if not os.path.exists(local_path):
    sys.exit(0)

tmp_target = None
try:
    fd, tmp_target = tempfile.mkstemp(prefix='cv_snap_', suffix='.tmp', dir=local_dir)
    os.close(fd)

    src = sqlite3.connect(local_path)
    dst = sqlite3.connect(tmp_target)
    with dst:
        src.backup(dst, pages=100)
    dst.close()
    src.close()

    check_conn = sqlite3.connect(tmp_target)
    integrity = check_conn.execute('PRAGMA integrity_check;').fetchone()
    check_conn.close()

    if integrity and integrity[0] == 'ok':
        tmp_persist = persist_path + '.tmp'
        shutil.copyfile(tmp_target, tmp_persist)
        os.replace(tmp_persist, persist_path)
        if os.path.exists(tmp_target):
            os.remove(tmp_target)
        with open(timestamp_file, 'w') as f:
            f.write(str(time.time()))
        sys.exit(0)
    else:
        sys.stderr.write('Integrity check on temporary snapshot failed!\n')
        if os.path.exists(tmp_target):
            os.remove(tmp_target)
        sys.exit(1)
except Exception as e:
    sys.stderr.write(f'Online backup failed: {e}\n')
    if tmp_target and os.path.exists(tmp_target):
        try:
            os.remove(tmp_target)
        except Exception:
            pass
    sys.exit(1)
"
    local status=$?
    if [ $status -eq 0 ]; then
        if [ "$is_shutdown" = "true" ]; then
            echo "✅ Final snapshot successfully validated and saved to ${PERSISTENT_DB}."
        fi
        return 0
    else
        echo "⚠️ WARNING: Online backup attempt failed with exit status ${status}!"
        return 1
    fi
}

# ------------------------------------------------------------------------------
# 3. Background Periodic Backup Daemon
# ------------------------------------------------------------------------------
PERIODIC_SYNC_INTERVAL="${DB_SYNC_INTERVAL_SECONDS:-60}"
(
    while true; do
        sleep "$PERIODIC_SYNC_INTERVAL"
        if ! perform_online_backup "false"; then
            echo "⚠️ [Daemon] Backup interval encountered an error. Will retry in ${PERIODIC_SYNC_INTERVAL}s."
        fi
    done
) &
BACKUP_DAEMON_PID=$!

# ------------------------------------------------------------------------------
# 4. Graceful Shutdown & Cleanup Handler
# ------------------------------------------------------------------------------
cleanup() {
    local exit_code="${1:-0}"
    # Temporarily disable exit-on-error so cleanup executes completely
    set +e

    echo ""
    echo "🛑 Stopping services and flushing final state (Exit Code: ${exit_code})..."

    # 1. Stop background periodic backup daemon first to avoid racing with final backup
    if [ -n "$BACKUP_DAEMON_PID" ] && kill -0 "$BACKUP_DAEMON_PID" 2>/dev/null; then
        kill "$BACKUP_DAEMON_PID" 2>/dev/null || true
        wait "$BACKUP_DAEMON_PID" 2>/dev/null || true
    fi

    # 2. Terminate Uvicorn FIRST so the application stops accepting and writing requests
    if [ -n "$UVICORN_PID" ] && kill -0 "$UVICORN_PID" 2>/dev/null; then
        echo "🛑 Terminating Uvicorn process..."
        kill -TERM "$UVICORN_PID" 2>/dev/null || true
        wait "$UVICORN_PID" 2>/dev/null || true
        echo "✅ Uvicorn stopped. All active writes completed."
    fi

    # 3. Take final atomic snapshot AFTER Uvicorn has exited cleanly
    echo "💾 Performing final atomic database snapshot to persistent storage..."
    if ! perform_online_backup "true"; then
        echo "🚨 CRITICAL: Final shutdown snapshot failed to write to persistent storage!"
    fi

    # 4. Stop Ollama daemon
    if [ -n "$OLLAMA_PID" ] && kill -0 "$OLLAMA_PID" 2>/dev/null; then
        echo "🛑 Terminating Ollama daemon..."
        kill -TERM "$OLLAMA_PID" 2>/dev/null || true
        for i in {1..6}; do
            if ! kill -0 "$OLLAMA_PID" 2>/dev/null; then break; fi
            sleep 0.5
        done
        kill -9 "$OLLAMA_PID" 2>/dev/null || true
        wait "$OLLAMA_PID" 2>/dev/null || true
        echo "✅ Ollama daemon stopped."
    fi

    exit "$exit_code"
}
trap 'cleanup 0' SIGTERM SIGINT

# ------------------------------------------------------------------------------
# 5. Start & Verify Ollama Readiness and Model Availability
# ------------------------------------------------------------------------------
# CORRECTION 4: Fail explicitly if Ollama fails or model is missing
if command -v ollama >/dev/null 2>&1; then
    echo "🦙 Starting Ollama daemon in background..."
    ollama serve &
    OLLAMA_PID=$!

    echo "⏳ Waiting for Ollama daemon to become ready..."
    OLLAMA_READY=false
    for i in {1..30}; do
        if curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
            OLLAMA_READY=true
            echo "✅ Ollama is ready."
            break
        fi
        sleep 1
    done

    if [ "$OLLAMA_READY" != "true" ]; then
        echo "❌ FATAL: Ollama daemon failed to start on 127.0.0.1:11434 within 30 seconds."
        cleanup 1
    fi

    # Verify model is available (baked into image)
    TARGET_MODEL="${OLLAMA_LLM_MODEL:-qwen2.5:1.5b}"
    echo "🔍 Verifying availability of model: ${TARGET_MODEL}..."
    MODEL_AVAILABLE=$(python3 -c "
import urllib.request, json, sys
try:
    with urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=5) as res:
        data = json.loads(res.read().decode())
        names = [m.get('name', '') for m in data.get('models', [])]
        if any('${TARGET_MODEL}' in n for n in names):
            sys.exit(0)
        else:
            sys.exit(1)
except Exception:
    sys.exit(1)
" 2>/dev/null && echo "yes" || echo "no")

    if [ "$MODEL_AVAILABLE" = "yes" ]; then
        echo "✅ Model ${TARGET_MODEL} is pre-baked and available for inference."
    else
        echo "⚠️ Model ${TARGET_MODEL} not detected in local store. Attempting one-time pull..."
        if ollama pull "$TARGET_MODEL"; then
            echo "✅ Model ${TARGET_MODEL} successfully pulled."
        else
            echo "❌ FATAL: Failed to obtain required model ${TARGET_MODEL}."
            cleanup 1
        fi
    fi
fi

# ------------------------------------------------------------------------------
# 6. Start FastAPI Backend via Uvicorn (Monitored in foreground)
# ------------------------------------------------------------------------------
# CORRECTION 3: Handle process failure without masking exit code or bypassing cleanup
echo "🐍 Starting Uvicorn backend on port ${PORT:-8000}..."
python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT:-8000}" &
UVICORN_PID=$!

# Wait for Uvicorn and capture its exit status explicitly
UVICORN_EXIT=0
wait "$UVICORN_PID" || UVICORN_EXIT=$?

if [ $UVICORN_EXIT -ne 0 ]; then
    echo "🚨 Uvicorn exited unexpectedly with code ${UVICORN_EXIT}!"
fi

cleanup "$UVICORN_EXIT"
