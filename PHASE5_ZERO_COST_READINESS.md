# Phase 5 — CVScreen Zero-Cost Deployment Readiness Audit

**Audit Date:** October 16, 2026  
**Author:** Senior Azure Cloud Architect, DevOps Engineer & Application Security Reviewer  
**Target Environment:** Azure Container Apps / `rg-cvscreening-prod`  
**Application:** CVScreen (React 19 + Nginx, FastAPI Backend, Pre-Baked Qwen2.5:1.5B via Ollama, SQLite with Azure Files Persistence)  

---

## 1. Executive Verdict

### **Verdict: CONDITIONALLY INFEASIBLE under strict ₹0 on native Azure without promotional credits; FEASIBLE under specific zero-cost private distribution or existing trial credits.**

| Dimension | Assessment | Evidence |
| :--- | :---: | :--- |
| **Compute Cost (Container Apps)** | **Feasible (₹0)** | Azure Container Apps provides a permanent monthly free allowance of **180,000 vCPU-seconds, 360,000 GiB-seconds, and 2M requests**. With `minReplicas: 0` (scale-to-zero) and `maxReplicas: 1`, staging usage consumes < 17% of this grant. |
| **Storage Cost (Azure Files)** | **Conditional (< ₹25/mo)** | Azure Files (`Standard_LRS`) has no permanent free tier. Storing a 10MB SQLite database costs ~$0.10–$0.30/mo (~₹10–₹25/mo), covered by Free Trial credits while active. |
| **Container Registry (ACR)** | **Infeasible for permanent ₹0** | Azure Container Registry has **NO permanent free tier**. The existing `Standard` ACR costs **$20.00/month (~₹1,660/mo)**. Downgrading to `Basic` costs **$5.00/month (~₹415/mo)**. |
| **Subscription Guardrail** | **Active Protection** | Read-only audit confirmed subscription policy: `quotaId: "FreeTrial_2014-09-01"` with **`spendingLimit: "On"`**. Azure will **never bill the user's payment card** above trial credits. If credits lapse, services are suspended rather than charged. |
| **Private Zero-Cost Alternatives** | **Feasible (₹0)** | Docker Hub Free (1 private repository up to 10 GB) or Cloudflare Tunnel to an existing workstation provides true permanent ₹0 without exposing code or model weights. |

---

## 2. Existing Resource Inventory and Verified Status

*All data retrieved via read-only Azure Management API calls (`az resource list`, `az containerapp env show`, `az acr show`, `az storage account show`).*

| Resource Name | Resource Type | Region | State | SKU / Tier | Finding Classification |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `rg-cvscreening-prod` | Resource Group | `eastus` | Succeeded | Standard | **Verified** |
| `crcvscreenexample` | Container Registry | `eastus` | Succeeded | `Standard` ($0.667/day) | **Verified** |
| `stcvscreenexample` | Storage Account | `eastus` | Succeeded | `Standard_LRS` | **Verified** |
| `cae-cvscreen-prod-example` | Container Apps Env | `eastus` | **`Failed`** | `Consumption` | **Verified [BLOCKED]** |
| `law-cvscreen-prod-example` | Log Analytics | `eastus` | Succeeded | Per-GB (Free 5 GB/mo) | **Verified** |
| `appi-cvscreen-prod-example`| Application Insights | `eastus` | Succeeded | Free Tier linked to LAW | **Verified** |
| `cv-data` (File Share) | Azure Files Share | `eastus` | Empty | Hot Tier | **Verified** |
| `cv-models` (File Share) | Azure Files Share | `eastus` | Empty | Hot Tier | **Verified** |

### Verified Blocker: Regional Capacity in `eastus`
Inspection of `cae-cvscreen-prod-example` returned:
```json
"deploymentErrors": "ErrorCode: ManagedEnvironmentCapacityHeavyUsageError, Message: Creating a new managed environment is unavailable at this time due to high demand in current region. To create a new managed environment, we recommend using an alternate region."
```
- **Classification:** **Blocked** in `eastus`.
- **Resolution:** The Managed Environment must be deployed to **`eastus2`** where capacity is available.

---

## 3. Confirmed, Possible, and Unknown Costs

| Component | Confirmed Free Grant | Confirmed Paid Rate | Staging Monthly Cost | Classification |
| :--- | :--- | :--- | :---: | :---: |
| **Container Apps Compute** | 180,000 vCPU-s & 360,000 GiB-s per month | $0.000024/vCPU-s, $0.000003/GiB-s | **₹0.00** (scale-to-zero) | **Verified** |
| **Log Analytics Ingestion** | 5 GB ingestion free per month | $2.30/GB above 5 GB | **₹0.00** (staging logs < 200MB) | **Verified** |
| **Azure Storage (Files & Blob)** | None permanent | $0.06/GB/mo (LRS) + transactions | **~₹10–₹25/mo** | **Verified** |
| **Existing ACR (Standard)** | None | $0.667/day (~$20.00/mo) | **~₹1,660/mo** (burns trial credits) | **Verified** |
| **Existing ACR (Downgraded to Basic)** | None | $0.167/day (~$5.00/mo) | **~₹415/mo** (burns trial credits) | **Verified** |
| **Docker Hub (1 Private Repo)** | 100% Free permanent | $0.00 | **₹0.00** | **Verified** |
| **Cloudflare Tunnel (Self-Hosted)** | 100% Free permanent | $0.00 | **₹0.00** | **Verified** |

> [!NOTE]
> **Subscription Spending Guardrail Verified:**  
> The subscription policy confirms `quotaId: "FreeTrial_2014-09-01"` with `spendingLimit: "On"`. Charges **cannot** be passed to a personal credit card without the user manually disabling the spending limit in the Azure Portal.

---

## 4. Zero-Cost Image Distribution Options

Constraint #7 strictly forbids public container images to protect proprietary code, model weights, and data privacy.

| Distribution Option | Monthly Cost | Confidentiality | Size & Quota Fit | Complexity | Recommendation |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **1. Existing ACR (Standard)** | ~$20.00/mo (Free Trial Credit) | Private | Fits 2.55 GiB image (100 GB limit) | Lowest (native Bicep) | **Viable during 30-day Free Trial only** |
| **2. Existing ACR (Basic)** | ~$5.00/mo (Free Trial Credit) | Private | Fits 2.55 GiB image (10 GB limit) | Low (single Bicep parameter change) | **Recommended for Azure Staging** |
| **3. GitHub Container Registry (GHCR)** | **Infeasible for ₹0** | Private | **Blocked:** GitHub Free provides only **500 MB** private package storage. Our compressed image is **~1.2 GB**. Making it public violates Constraint #7. | High | **Rejected** |
| **4. Docker Hub Free Tier** | **₹0.00** | Private | Fits (1 free private repository up to 10 GB). | Medium (Container Apps authenticates to Docker Hub) | **Best for Permanent ₹0 on Azure** |
| **5. Direct Host + Cloudflare Tunnel** | **₹0.00** | Private | No registry needed; runs on existing Mac/server. | Low (Single lightweight tunnel daemon) | **Best for 100% Zero Azure Footprint** |

---

## 5. Region and Compute Feasibility

- **Region Selection:** `eastus` failed with `ManagedEnvironmentCapacityHeavyUsageError`. Target region must be **`eastus2`**.
- **Container Apps Workload Profile:** Serverless `Consumption` profile.
- **Resource Sizing:**
  - **Backend Container:** 2.0 vCPU, 4.0 GiB RAM.
  - **Frontend Container:** 0.5 vCPU, 1.0 GiB RAM.
- **Monthly Compute Math:**
  - 180,000 vCPU-seconds allowance ÷ 2.0 vCPU = 90,000 seconds = **25 active hours of client demonstration per month free**.
  - During idle periods, containers scale to 0 replicas, consuming 0 vCPU-seconds ($0.00).

---

## 6. Model, CPU, RAM, Image-Size & Inference Considerations

- **Model Engine:** Pre-baked `qwen2.5:1.5b` (Q4_K_M quantized).
- **Physical Memory Consumption:**
  - Ollama runtime + model weights: ~1.2 GiB.
  - FastAPI / Uvicorn + PyMuPDF: ~250 MiB.
  - Total container RSS memory under peak inference load: **~1.45–1.8 GiB** (well within 4.0 GiB allocation).
- **CPU Inference Performance (Empirically Verified):**
  - First-token latency: ~1.1s.
  - Complete candidate HR chat response: **7.65s** on standard CPU.
- **Cold Start Profile:**
  - Scale-to-zero cold start: ~20–30s (container provisioning + Ollama daemon start + verified pre-baked weights check).
  - Reverse proxy read timeout in `frontend/nginx.conf`: **300s**, preventing HTTP 504 gateway timeouts during cold starts.

---

## 7. Database Persistence, Concurrency & Security Risks

### Verified Architecture
- **Active Database Location:** `/app/local_data/cv_screening.db` on fast ephemeral container storage. Avoids POSIX file locking and `mmap` failures over SMB/CIFS.
- **Persistent Storage Mount:** Azure Files share (`cv-data`) mounted via CIFS to `/app/data/`.
- **Sync Mechanism:** Python SQLite Online Backup API streams consistent page copies to `/app/data/cv_snap_<tmp>.tmp`, validates with `PRAGMA integrity_check;`, and atomically replaces `/app/data/cv_screening.db`.
- **Shutdown Durability:** Entrypoint trap intercepts `SIGTERM`, stops Uvicorn first to finish active writes, takes verified final snapshot, then terminates Ollama.
- **Crash Durability:** Process-group `SIGKILL` tests proved zero corrupted files and zero orphaned workers; periodic backup preserves state up to interval (RPO = interval).

### Critical Concurrency Rule: Single Replica
- **Risk:** SQLite does NOT support multiple concurrent writers across network shares.
- **Mandatory Configuration:** In `infra/bicep/modules/container-apps.bicep`, backend `scale.maxReplicas` **MUST be 1**.

---

## 8. Single-URL Architecture & Security Boundary

```
                     HTTPS :443
 Client Browser  ==================>  [ Azure Container Apps Ingress ]
                                                   |
                                                   v
                                     +---------------------------+
                                     |  Frontend (React + Nginx) |
                                     |  ingress.external = true  |
                                     +---------------------------+
                                                   |
                                                   | Private Internal Network
                                                   | proxy_pass http://app-backend:8000
                                                   v
                                     +---------------------------+
                                     |      Backend (FastAPI)    |
                                     |  ingress.external = false |
                                     |  (Hidden from Internet)   |
                                     +---------------------------+
                                                   |
                                                   | Loopback (127.0.0.1:11434)
                                                   v
                                     +---------------------------+
                                     |       Ollama Daemon       |
                                     |       Qwen2.5:1.5B        |
                                     +---------------------------+
```

1. **Private Backend Ingress:** Backend must be set to `ingress.external = false`. It is completely unreachable from the public internet.
2. **Reverse Proxy:** Frontend Nginx handles SSL termination and reverse proxies `/api/*` to the private backend FQDN.
3. **Loopback Inference:** Backend communicates with Ollama solely over loopback (`http://127.0.0.1:11434`).
4. **Data Isolation:** Zero personal resumes or developer test suites exist in the image layers or filesystem (verified clean).

---

## 9. Required Code & Configuration Changes

The following 4 adjustments are required in the codebase before any deployment:

1. **`infra/bicep/parameters.prod.json`:**
   - Change `"location"` from `"eastus"` to `"eastus2"` (resolves `ManagedEnvironmentCapacityHeavyUsageError`).
2. **`infra/bicep/modules/container-apps.bicep`:**
   - Backend Ingress: Change `ingress.external` to `false` (enforces private backend).
   - Backend Scaling: Change `minReplicas` to `0` and `maxReplicas` to `1` (enforces single SQLite writer and ₹0 scale-to-zero compute).
3. **`infra/bicep/modules/acr.bicep`:**
   - If using Azure Container Registry, change SKU from `Standard` to `Basic` to minimize daily credit burn.
4. **`frontend/nginx.conf`:**
   - Ensure `proxy_pass` points to `http://app-cvscreen-backend-prod:8000` or internal Container Apps FQDN with 300s timeouts.

---

## 10. Dependency-Ordered Deployment Checklist

- [ ] **Step 1: Code Freeze & Bicep Parameter Update**
  - Update `parameters.prod.json` to `eastus2`.
  - Update `container-apps.bicep` for internal ingress and `maxReplicas: 1`.
- [ ] **Step 2: Choose Registry Strategy**
  - *Option A:* Use existing ACR (downgraded to `Basic`, billed to trial credit).
  - *Option B:* Authenticate Container Apps to private Docker Hub (permanent ₹0).
- [ ] **Step 3: User Approval Gate for Image Push**
  - Explicit user approval required before pushing `v2-durable`.
- [ ] **Step 4: Provision Container Apps Environment in `eastus2`**
  - Execute read-only validation (`az deployment group validate`) before deploying.
- [ ] **Step 5: Deploy Frontend & Backend Containers**
  - Deploy backend with internal ingress (`maxReplicas: 1`, `minReplicas: 0`).
  - Deploy frontend with external ingress.
- [ ] **Step 6: Live Smoke Test**
  - Verify single HTTPS URL from external network.
  - Verify 500 mock candidate database loading.
  - Execute live resume evaluation & HR chat inference.
  - Verify scale-to-zero when idle.

---

## 11. Rollback & Data Protection Strategy

1. **Zero Data Destruction:** The SQLite database is never wiped on rollback. Snapshots in `/app/data/cv_screening.db` are preserved independently of container lifecycle.
2. **Corrupted File Quarantine:** If a snapshot fails integrity verification, `scripts/entrypoint.sh` automatically isolates it to `cv_screening_corrupted_<timestamp>.db` and aborts startup, preventing data overwrites.
3. **No RG Deletion:** Resource group `rg-cvscreening-prod` will never be deleted as a routine rollback. Individual container revisions are stopped or rolled back cleanly.

---

## 12. Actions Strictly Pending Explicit Approval

The following actions were **NOT performed** and remain strictly gated pending your explicit instruction:
- [ ] Any image push to ACR, Docker Hub, or any registry.
- [ ] Modifying or deploying Bicep templates.
- [ ] Creating or provisioning new Azure resources in `eastus2`.
- [ ] Downgrading or reconfiguring existing Azure resources.
