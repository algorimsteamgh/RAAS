import os
import sys
import time
import signal
import sqlite3
import subprocess
import shutil
import tempfile

test_root = tempfile.mkdtemp(prefix="cv_crash_test_")
PERSISTENT_DIR = os.path.join(test_root, "persistent")
LOCAL_DIR = os.path.join(test_root, "local")
PERSISTENT_DB = os.path.join(PERSISTENT_DIR, "cv_screening.db")
LOCAL_DB = os.path.join(LOCAL_DIR, "cv_screening.db")

os.makedirs(PERSISTENT_DIR, exist_ok=True)
os.makedirs(LOCAL_DIR, exist_ok=True)

print(f"=== Abrupt Process Group Crash Test ===")
print(f"Test Root:      {test_root}")
print(f"Persistent Dir: {PERSISTENT_DIR}")
print(f"Local Dir:      {LOCAL_DIR}")

proc = None
pgid = None

def terminate_pg():
    global proc, pgid
    if pgid:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if proc:
        try:
            proc.wait(timeout=2.0)
        except Exception:
            pass

try:
    env = os.environ.copy()
    env["PERSISTENT_DATA_DIR"] = PERSISTENT_DIR
    env["DATABASE_PATH"] = LOCAL_DB
    env["PORT"] = "8099"
    # Set periodic sync interval to 2 seconds for deterministic testing
    env["DB_SYNC_INTERVAL_SECONDS"] = "2"

    # Launch entrypoint in a brand-new process group
    proc = subprocess.Popen(
        ["bash", "/Users/apple/cvscreening/scripts/entrypoint.sh"],
        env=env,
        preexec_fn=os.setsid,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    pgid = os.getpgid(proc.pid)
    print(f"Spawned entrypoint PID: {proc.pid}, PGID: {pgid}")

    # 1. Wait for Uvicorn & Database initialization
    print("Waiting for application and database initialization...")
    ready = False
    for _ in range(25):
        time.sleep(1)
        if os.path.exists(LOCAL_DB):
            try:
                conn = sqlite3.connect(LOCAL_DB)
                res = conn.execute("SELECT count(*) FROM candidates").fetchone()
                conn.close()
                if res and res[0] >= 0:
                    ready = True
                    print(f"Database ready with {res[0]} initial records.")
                    break
            except Exception:
                pass

    if not ready:
        raise RuntimeError("Application failed to initialize working database.")

    # 2. Insert Candidate 1 (Must be synced by periodic daemon)
    conn = sqlite3.connect(LOCAL_DB)
    conn.execute(
        "INSERT INTO candidates (candidate_id, full_name, email) VALUES (?, ?, ?)",
        ("CAND-CRASH-SYNCED", "Candidate Flushed By Periodic Sync", "flushed@example.com")
    )
    conn.commit()
    conn.close()
    print("Inserted 'CAND-CRASH-SYNCED' into local working DB.")

    # 3. Wait for periodic sync interval to run and produce verified snapshot
    print("Sleeping 3.5s to ensure periodic sync daemon executes...")
    time.sleep(3.5)

    if not os.path.exists(PERSISTENT_DB):
        raise RuntimeError(f"Periodic sync failed to create {PERSISTENT_DB}")

    p_conn = sqlite3.connect(PERSISTENT_DB)
    synced_cnt = p_conn.execute("SELECT count(*) FROM candidates WHERE candidate_id='CAND-CRASH-SYNCED'").fetchone()[0]
    p_conn.close()
    print(f"Verified 'CAND-CRASH-SYNCED' exists in persistent snapshot: count={synced_cnt}")
    assert synced_cnt == 1, "Candidate was not captured by periodic sync!"

    # 4. Insert Candidate 2 (Written right before crash, within next sync window)
    conn = sqlite3.connect(LOCAL_DB)
    conn.execute(
        "INSERT INTO candidates (candidate_id, full_name, email) VALUES (?, ?, ?)",
        ("CAND-CRASH-MIDFLIGHT", "Candidate Midflight Before Crash", "midflight@example.com")
    )
    conn.commit()
    conn.close()
    print("Inserted 'CAND-CRASH-MIDFLIGHT' into local DB immediately prior to SIGKILL.")

    # Record snapshot mtime
    snapshot_mtime_before = os.path.getmtime(PERSISTENT_DB)

    # 5. Send SIGKILL to the entire process group
    print(f"Simulating abrupt container crash: sending SIGKILL to entire process group -{pgid}...")
    os.killpg(pgid, signal.SIGKILL)
    try:
        proc.wait(timeout=2.0)
    except Exception:
        pass
    time.sleep(1.0)

    # 6. Verify zero surviving processes in the process group
    print(f"Checking process table for any surviving processes in PGID {pgid}...")
    ps_check = subprocess.run(["ps", "-o", "pid,ppid,pgid,state,command", "-ax"], capture_output=True, text=True)
    surviving = [line for line in ps_check.stdout.splitlines() if f" {pgid} " in line and "<defunct>" not in line]

    if surviving:
        print("SURVIVING PROCESSES IN PGID:\n" + "\n".join(surviving))
        raise RuntimeError("Processes in process group survived SIGKILL!")
    else:
        print(f"CONFIRMED: Zero active processes surviving in PGID {pgid}.")

    # Verify no worker process references this test directory
    orphan_check = subprocess.run(["pgrep", "-f", test_root], capture_output=True, text=True)
    if orphan_check.stdout.strip():
        print(f"Orphaned workers detected: {orphan_check.stdout.strip()}")
        raise RuntimeError("Orphaned workers running!")
    else:
        print("CONFIRMED: Zero orphaned background workers referencing test directory.")

    # 7. Wait 3 seconds to confirm snapshot is completely frozen
    time.sleep(3.0)
    snapshot_mtime_after = os.path.getmtime(PERSISTENT_DB)
    assert snapshot_mtime_before == snapshot_mtime_after, "Persistent snapshot was modified after crash!"
    print("CONFIRMED: Persistent snapshot was not modified after crash (no delayed writes).")

    # 8. Check persistent database integrity and state
    print("Inspecting persistent database snapshot...")
    p_conn = sqlite3.connect(PERSISTENT_DB)
    integ = p_conn.execute("PRAGMA integrity_check;").fetchone()
    print(f"Snapshot integrity check: {integ[0]}")
    assert integ[0] == "ok", f"Corrupt snapshot! {integ}"

    c1 = p_conn.execute("SELECT count(*) FROM candidates WHERE candidate_id='CAND-CRASH-SYNCED'").fetchone()[0]
    c2 = p_conn.execute("SELECT count(*) FROM candidates WHERE candidate_id='CAND-CRASH-MIDFLIGHT'").fetchone()[0]
    p_conn.close()

    print(f"Periodic sync record ('CAND-CRASH-SYNCED'): count={c1} (Expected: 1)")
    print(f"Mid-flight record ('CAND-CRASH-MIDFLIGHT'): count={c2} (Expected: 0, unsynced prior to abrupt crash)")

    assert c1 == 1, "Periodic sync record missing!"
    assert c2 == 0, "Mid-flight record was written, which implies graceful shutdown or surviving worker ran!"

    print("\n-----------------------------------------------------------")
    print("✅ CRASH DURABILITY AUDIT PASSED:")
    print("1. Process group terminated cleanly with SIGKILL.")
    print("2. No child worker survived to perform delayed writes.")
    print("3. Periodic sync guaranteed data durability up to the sync interval.")
    print("4. SQLite Online Backup + atomic rename prevented corruption on crash.")
    print("-----------------------------------------------------------")

finally:
    terminate_pg()
    shutil.rmtree(test_root, ignore_errors=True)
