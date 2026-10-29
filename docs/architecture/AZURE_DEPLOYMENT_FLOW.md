# CVScreen: Azure Production Deployment & Networking Flow

**Document**: `AZURE_DEPLOYMENT_FLOW.md`  
**Environment**: Production (`rg-cvscreening-prod` / Region: East US 2)  
**Architecture**: Serverless Microservices via Azure Container Apps (ACA)  
**Security Posture**: Zero Cloud Leakage, Private Internal Ingress, Encrypted Storage  

---

## 1. Cloud Architecture Overview

CVScreen is hosted inside a single **Azure Container Apps Managed Environment** (`cae-cvscreen-prod-eastus2-example`). This provides a managed Kubernetes substrate without the operational overhead of a full AKS cluster.

```
[ Internet ]
     │
     │ HTTPS (TLS 1.3)
     ▼
[ Azure Edge Managed Ingress ]
     │
     │ Port 80
     ▼
[ Frontend Container App (app-cvscreen-frontend-prod) ]
  • Public Ingress: YES
  • FQDN: app-cvscreen-frontend-prod.braveglacier-819095d3.eastus2.azurecontainerapps.io
  • Container: Nginx 1.25 Alpine + React 19 Build
     │
     │ Internal VNet Routing (HTTP / Port 8000)
     ▼
[ Backend Container App (app-cvscreen-backend-prod) ]
  • Public Ingress: NO (Internal only)
  • FQDN: app-cvscreen-backend-prod.internal.braveglacier-819095d3.eastus2.azurecontainerapps.io
  • Container: Python 3.11 + FastAPI + Uvicorn + Ollama Qwen 2.5
  • Local Ephemeral Storage: /app/local_data (SSD fast reads/writes)
     │
     │ CIFS / SMB Mount
     ▼
[ Azure Storage Account File Share ]
  • Resource: stcvscreenprodxg4dry2ol / Share: cvdatamount
  • Mount Point: /app/data
  • Holds: cv_screening.db (Durable SQLite backup snapshot)
```

---

## 2. Ingress & Traffic Flow

### A. How the Browser Reaches the Frontend
1. The user requests `https://app-cvscreen-frontend-prod.braveglacier-819095d3.eastus2.azurecontainerapps.io/`.
2. DNS resolves to the public virtual IP allocated to the Container Apps Managed Environment.
3. Microsoft's edge envoy proxy terminates TLS using a managed wildcard certificate (`*.azurecontainerapps.io`).
4. The edge proxy forwards decrypted HTTP traffic to the `frontend` container on target port 80.
5. Nginx serves the React single-page application bundle (`index.html`, JavaScript, CSS).

### B. How Nginx Reaches the Private Backend
1. When the React app makes an API call (e.g. `POST /api/upload-cv`), it issues a relative request: `/api/upload-cv`.
2. Nginx captures all `/api/*` paths via its configuration:
   ```nginx
   location /api/ {
       proxy_pass ${BACKEND_URL};
       proxy_http_version 1.1;
       proxy_read_timeout 300s;
       proxy_connect_timeout 75s;
   }
   ```
3. In production, `${BACKEND_URL}` is injected via container environment variables to:
   `http://app-cvscreen-backend-prod.internal.braveglacier-819095d3.eastus2.azurecontainerapps.io:8000`.
4. The request travels over the Azure internal virtual network. **The backend container has no public IP address and cannot be accessed directly from the internet.**

---

## 3. Co-Located AI Model Inference

### How the Backend Invokes the Local Ollama Model
1. In standard cloud architectures, an LLM call traverses the public internet to an OpenAI or Anthropic API, incurring per-token billing, latency, and data privacy risks.
2. In CVScreen, **Ollama runs inside the exact same container as FastAPI**:
   - Both processes are launched by `/app/entrypoint.sh`.
   - Ollama listens exclusively on `127.0.0.1:11434`.
   - FastAPI communicates with Ollama over loopback (`localhost`).
3. Model weights (`qwen2.5:1.5b`, ~986MB) are pre-baked into the container image layer during `docker build`.
4. The container requires **zero internet access at runtime** to perform resume extraction, explainable scoring, or HR chat inference.

---

## 4. Storage Architecture & Persistence

Running SQLite in containerized environments requires addressing two core challenges:
1. Containers are ephemeral: if a container crashes or scales to zero, local container storage is wiped.
2. Network file shares (CIFS/NFS) have high latency and POSIX file lock issues that corrupt SQLite databases if written to directly under high concurrency.

### The Two-Tier Storage Solution
CVScreen implements an **active-passive hybrid storage architecture**:

```
[ FastAPI App ]
       │
       │ Fast read/write (Microsecond latency)
       ▼
[ Tier 1: Local Ephemeral NVMe ]
  Path: /app/local_data/cv_screening.db
  Mode: PRAGMA journal_mode=WAL
       │
       │ Periodic Online Backup (every 60s via entrypoint daemon)
       │ Uses python sqlite3.backup() API with PRAGMA integrity_check
       ▼
[ Tier 2: Durable Azure Files Share ]
  Storage Name: cvdatamount
  Azure Path: stcvscreenprodxg4dry2ol.file.core.windows.net/cvdatamount
  Mount Point: /app/data/cv_screening.db
```

### Startup Restoration Flow (`scripts/entrypoint.sh`):
1. When the backend container boots, it checks if `/app/data/cv_screening.db` exists on the Azure File share.
2. If found, it runs an integrity check (`PRAGMA integrity_check`).
3. If verified, it copies the snapshot to `/app/local_data/cv_screening.db` on fast ephemeral storage before starting Uvicorn.
4. If the snapshot is corrupted, it moves the corrupted file to a `.corrupted_backup` quarantine and halts, protecting data integrity.

### Graceful Shutdown Trap:
- A `SIGTERM` trap in `entrypoint.sh` intercepts Azure scaling/restart signals:
  ```bash
  trap 'cleanup 0' SIGTERM SIGINT
  ```
- Before terminating, the script pauses incoming requests, halts the background daemon, flushes SQLite WAL logs, and writes an atomic final backup to `/app/data/cv_screening.db`.

---

## 5. Container Registry (ACR) Integration

- **Registry Name**: `crcvscreenexample.azurecr.io` (Standard SKU).
- **Authentication**: Managed via secure admin password secret references in the Container App environment:
  - Secret: `acr-password`
  - Server: `crcvscreenexample.azurecr.io`
- **Images**:
  - `crcvscreenexample.azurecr.io/cvscreening-frontend:latest`
  - `crcvscreenexample.azurecr.io/cvscreening-backend:latest`
- **Build Pipeline**: Built locally with `--platform linux/amd64` using Docker Desktop and pushed directly to ACR. (ACR Cloud Tasks are disabled on Azure Free Trial subscriptions due to `TasksOperationsNotAllowed` quota restrictions).

---

## 6. Health Checks & Container Probes

Both container apps define active HTTP probes to monitor health and manage routing:

| Container | Probe Type | Endpoint | Port | Initial Delay | Period | Timeout | Failure Threshold |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Frontend** | Liveness | `/healthz` | 80 | 5s | 30s | 3s | 3 |
| **Backend** | Startup / Readiness | `/api/system/health` | 8000 | 10s | 15s | 5s | 5 |
| **Backend** | Liveness | `/api/system/health` | 8000 | 20s | 30s | 5s | 5 |

### Backend Readiness Verification
`/api/system/health` performs a live check:
```json
{
  "ollama_status": "connected",
  "ollama_model": "qwen2.5:1.5b",
  "ollama_url": "http://127.0.0.1:11434",
  "parser_status": "ready",
  "database_status": "ready",
  "version": "3.0.0"
}
```
Azure will not route incoming user traffic to the backend until all sub-systems (database and Ollama daemon) respond with HTTP 200.

---

## 7. Failure Scenarios & Scaling Behavior

### A. Scale-to-Zero Cold Start
- The backend container is configured with `minReplicas: 0, maxReplicas: 1` to comply with Azure Free Trial consumption quotas and minimize costs.
- When inactive for $>300$ seconds, the backend pod shuts down after flushing its final SQLite backup to Azure Files.
- When a user uploads a CV or opens the page, the HTTP request triggers ACA to provision a new backend replica.
- **Cold Start Duration**: ~15–20 seconds (Ollama daemon launch + DB restoration from Azure Files). Once warmed, subsequent requests process immediately.

### B. Container Crash / OOM Recovery
- If the Python process encounters an unexpected unhandled exception or memory spike, Azure Container Apps detects the failed liveness probe.
- ACA terminates the unhealthy pod and starts a fresh instance from ACR.
- On startup, the new container mounts `/app/data`, verifies the database integrity, restores the database, and resumes serving without data loss.
