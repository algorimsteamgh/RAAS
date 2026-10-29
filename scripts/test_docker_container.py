import os
import sys
import time
import json
import sqlite3
import urllib.request
import subprocess
import shutil

TEST_DIR = "/tmp/cv_docker_test"
PERSISTENT_DATA = f"{TEST_DIR}/data"
CONTAINER_NAME = "cv_test_durable_container"
HOST_PORT = "8088"

def cleanup():
    subprocess.run(["docker", "rm", "-f", CONTAINER_NAME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR, ignore_errors=True)

cleanup()
os.makedirs(PERSISTENT_DATA, exist_ok=True)

print("=================================================================")
print("  E2E Local Docker Container Test: cvscreening-backend:v2-durable")
print("=================================================================")

try:
    # 1. Run the container
    print(f"\n[1/6] Launching container '{CONTAINER_NAME}' on port {HOST_PORT}...")
    run_cmd = [
        "docker", "run", "-d",
        "--name", CONTAINER_NAME,
        "-p", f"{HOST_PORT}:8000",
        "-v", f"{PERSISTENT_DATA}:/app/data",
        "-e", "PORT=8000",
        "-e", "DB_SYNC_INTERVAL_SECONDS=5",
        "cvscreening-backend:v2-durable"
    ]
    container_id = subprocess.check_output(run_cmd, text=True).strip()
    print(f"Container ID: {container_id[:12]}")

    # 2. Wait for startup & health check
    print("\n[2/6] Waiting for container health check (FastAPI + Ollama)...")
    health_url = f"http://127.0.0.1:{HOST_PORT}/api/system/health"
    healthy = False
    for i in range(30):
        time.sleep(2)
        try:
            with urllib.request.urlopen(health_url, timeout=3) as res:
                if res.status == 200:
                    data = json.loads(res.read().decode())
                    print(f"Health check succeeded (Attempt {i+1}): {data}")
                    healthy = True
                    break
        except Exception:
            pass

    if not healthy:
        logs = subprocess.run(["docker", "logs", CONTAINER_NAME], capture_output=True, text=True)
        print("CONTAINER LOGS ON FAILURE:\n", logs.stdout, logs.stderr)
        raise RuntimeError("Container failed health check within 60 seconds.")

    # 3. Verify Synthetic Candidate Seeding
    print("\n[3/6] Verifying synthetic candidate database...")
    candidates_url = f"http://127.0.0.1:{HOST_PORT}/api/candidates"
    with urllib.request.urlopen(candidates_url, timeout=5) as res:
        candidates = json.loads(res.read().decode())
        cand_list = candidates.get("candidates", candidates) if isinstance(candidates, dict) else candidates
        total_cands = len(cand_list)
        print(f"Loaded candidates count: {total_cands}")
        assert total_cands == 500, f"Expected 500 synthetic candidates, got {total_cands}"

    # 4. Test Live AI Inference (Qwen2.5:1.5B via Ollama)
    print("\n[4/6] Testing AI Inference with pre-baked Qwen2.5:1.5B...")
    chat_url = f"http://127.0.0.1:{HOST_PORT}/api/candidates/CAND-0001/chat"
    chat_payload = json.dumps({
        "message": "Briefly state 2 key technical strengths of this candidate in one sentence.",
        "candidate_id": "CAND-0001"
    }).encode("utf-8")
    req = urllib.request.Request(chat_url, data=chat_payload, headers={"Content-Type": "application/json"})
    
    inference_start = time.time()
    with urllib.request.urlopen(req, timeout=30) as res:
        chat_resp = json.loads(res.read().decode())
        inference_dur = time.time() - inference_start
        print(f"Inference response received in {inference_dur:.2f}s:")
        print(f"AI Response: {chat_resp.get('response', chat_resp)}")
        assert "reply" in chat_resp or "response" in chat_resp, "Invalid inference response structure"

    # 5. Wait for periodic sync interval and test Graceful Shutdown
    print("\n[5/6] Testing graceful shutdown (SIGTERM) and final database flush...")
    time.sleep(3) # allow a sync cycle
    stop_cmd = ["docker", "stop", "-t", "15", CONTAINER_NAME]
    subprocess.check_call(stop_cmd)
    print("Container stopped successfully.")

    # Inspect container shutdown logs
    logs = subprocess.run(["docker", "logs", CONTAINER_NAME], capture_output=True, text=True).stdout
    print("\nContainer Shutdown Log Snippet:")
    for line in logs.splitlines()[-15:]:
        print(f"  {line}")

    assert "Uvicorn stopped. All active writes completed." in logs, "Uvicorn did not shut down cleanly in log"
    assert "Final snapshot successfully validated and saved" in logs, "Final snapshot log missing"

    # Verify persistent database snapshot on host
    persistent_db = f"{PERSISTENT_DATA}/cv_screening.db"
    assert os.path.exists(persistent_db), f"Persistent DB not found at {persistent_db}"
    conn = sqlite3.connect(persistent_db)
    integ = conn.execute("PRAGMA integrity_check;").fetchone()
    cands_count = conn.execute("SELECT count(*) FROM candidates").fetchone()[0]
    chat_count = conn.execute("SELECT count(*) FROM candidate_chat_messages").fetchone()[0]
    conn.close()

    print(f"\nPersistent DB snapshot integrity: {integ[0]}")
    print(f"Persistent DB candidates count:   {cands_count}")
    print(f"Persistent DB chat messages count: {chat_count}")

    assert integ[0] == "ok", "Persistent DB failed integrity check"
    assert cands_count == 500, f"Expected 500 candidates, got {cands_count}"
    assert chat_count >= 1, "Chat message from inference test was not persisted in database snapshot!"

    # 6. Test Container Restart & Database Restoration
    print("\n[6/6] Testing container restart & restoration from persistent snapshot...")
    # Remove old container
    subprocess.run(["docker", "rm", CONTAINER_NAME], check=True)
    # Start fresh container with the existing persistent volume
    subprocess.check_call(run_cmd)

    healthy = False
    for i in range(25):
        time.sleep(2)
        try:
            with urllib.request.urlopen(health_url, timeout=3) as res:
                if res.status == 200:
                    healthy = True
                    break
        except Exception:
            pass
    assert healthy, "Restarted container failed health check"

    restart_logs = subprocess.run(["docker", "logs", CONTAINER_NAME], capture_output=True, text=True).stdout
    print("Restart Log Snippet:")
    for line in restart_logs.splitlines()[:15]:
        print(f"  {line}")

    assert "Restoring verified snapshot to working database" in restart_logs or "Database restored successfully" in restart_logs, "Database restore log missing on restart"

    # Verify chat history survived the container restart
    with urllib.request.urlopen(f"http://127.0.0.1:{HOST_PORT}/api/candidates/CAND-0001/chat-history", timeout=5) as res:
        history = json.loads(res.read().decode())
        print(f"Restored chat history count: {len(history)}")
        assert len(history) >= 1, "Chat history lost across container restarts!"

    # Final cleanup of running test container
    subprocess.run(["docker", "stop", "-t", "5", CONTAINER_NAME], stdout=subprocess.DEVNULL)
    subprocess.run(["docker", "rm", CONTAINER_NAME], stdout=subprocess.DEVNULL)

    print("\n=================================================================")
    print("🎉 ALL PHASE 3 CONTAINER VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=================================================================")

finally:
    cleanup()
