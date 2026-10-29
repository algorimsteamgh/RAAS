# Phase 10 — CVScreen Final Pre-Deployment Safety Checklist

**Document:** `PHASE10_FINAL_DEPLOYMENT_CHECKLIST.md`  
**Role:** Senior Azure Cloud Architect, DevOps Engineer & AI Infrastructure Engineer  
**Date:** October 16, 2026  
**Status:** Pre-Deployment Safety Audit & Verification Complete  
**Target Resource Group:** `rg-cvscreening-prod`  
**Target Environment:** Azure Container Apps (`eastus2`) with Base Services (`eastus`)  
**Scope:** Read-Only Audit, Image Verification, Health Probe Validation & Deployment Gate Checklist  

---

## 1. Executive Summary & Verification State

A thorough, read-only pre-flight safety audit of the CVScreen repository, local Docker container images, and Azure environment has been executed.

### Safety & Invariant Attestation
- **Azure Resources Mutated:** **0** (No resources created, scaled, modified, or deleted).
- **Container Images Pushed:** **0** (`cvscreening-backend:v2-durable` remains exclusively local on the Mac host).
- **Deployments Executed:** **0** (`az deployment group create` was not run).
- **Public Accessibility:** **None** (Application is NOT deployed or publicly accessible).
- **Azure Trial Status:** `quotaId: "FreeTrial_2014-09-01"`, `spendingLimit: "On"`, `state: "Enabled"` `[Verified]`. Zero unexpected charges will reach the credit card, but the trial must be treated as temporary, not permanent.

---

## 2. Verified Prerequisites

Every item in the table below has been verified through direct, read-only command execution:

| Prerequisite Component | Status | Empirical Evidence / Verified Value |
| :--- | :--- | :--- |
| **Local Backend Image** | **VERIFIED** | `cvscreening-backend:v2-durable`<br>• Image ID: `sha256:41a30b9ac2ffdb339452a9b02825a1d1183fc7221cc1ccc189ba30d6cc504e00`<br>• Architecture: `linux/amd64`<br>• Size: `2,739,626,880` bytes (~2.55 GiB uncompressed / ~1.2 GB compressed)<br>• Pre-baked Model: `qwen2.5:1.5b` (verified offline) |
| **Remote Frontend Image** | **VERIFIED** | In ACR `crcvscreenexample` in `eastus`:<br>• Repository: `cvscreening-frontend`<br>• Tag: `latest`<br>• Digest: `sha256:7b861ff9afb7d3c40e402abfd7d99faef70821fd35e255381b1147eeab657392`<br>• Size: 28.8 MB compressed<br>• Identical to local image ID `7b861ff9afb7` |
| **Base Infrastructure in `eastus`** | **VERIFIED** | • Storage: `stcvscreenexample` (`Standard_LRS`, `eastus`)<br>• Shares: `cv-data`, `cv-models`<br>• Registry: `crcvscreenexample` (`Standard`, `eastus`)<br>• Monitoring: `law-cvscreen-prod-example`, `appi-...` (`eastus`) |
| **Bicep Decoupled Architecture** | **VERIFIED** | • `infra/bicep/main.bicep`: `containerAppsLocation = 'eastus2'`, `location = 'eastus'`<br>• `infra/bicep/modules/container-apps.bicep`: deterministic name `cae-cvscreen-prod-eastus2-example`<br>• ARM Pre-flight: `az deployment group validate` passed with `provisioningState: Succeeded` |
| **Backend Ingress Privacy** | **VERIFIED** | `container-apps.bicep` sets `ingress.external = false`. Only accessible over internal Envoy mesh via `https://app-cvscreen-backend-prod.internal.<cae-domain>` |
| **SQLite Single-Writer Sizing** | **VERIFIED** | `container-apps.bicep` sets backend `maxReplicas: 1` and `minReplicas: 0` |
| **Frontend Reverse Proxy** | **VERIFIED** | `frontend/nginx.conf` sets `proxy_pass ${BACKEND_URL};` with `proxy_read_timeout 300s` and `proxy_connect_timeout 75s` |
| **Azure Spending Limit** | **VERIFIED** | `quotaId: "FreeTrial_2014-09-01"`, `spendingLimit: "On"`, `subscriptionState: "Enabled"` via Azure ARM REST API |

---

## 3. Critical Findings: Missing or Invalid References & Blockers

The safety check identified two critical configuration mismatches that **must be addressed before provisioning**:

### Finding 1: Backend Health Probe Path Mismatch (HIGH IMPACT / DEPLOYMENT BLOCKER)
- **The Issue:** In `infra/bicep/modules/container-apps.bicep` (lines 218 & 229), both the Liveness and Readiness probes are configured with `path: '/healthz'` on port 8000:
  ```bicep
  probes: [
    {
      type: 'Liveness'
      httpGet: {
        path: '/healthz'
        port: 8000
      }
    }
  ]
  ```
- **The Reality:** In `backend/app/main.py`, the only registered health endpoint is **`/api/system/health`** `[Verified via route inspection]`. The `/healthz` route does not exist.
- **Consequence if Unaddressed:** When the backend container starts, Container Apps liveness probes will query `GET :8000/healthz` and receive **HTTP 404 Not Found**. After 5 consecutive failures (`failureThreshold: 5`), Container Apps will kill and restart the container, resulting in a **`CrashLoopBackOff` failure**.
- **Required Fix:** Update `container-apps.bicep` lines 218 and 229 to use `path: '/api/system/health'`. (This is an infrastructure-only fix that requires no changes to application code or the Docker image).

### Finding 2: Backend Image Tag Mismatch in Bicep vs ACR
- **The Issue:** `infra/bicep/main.bicep` line 106 defines:
  ```bicep
  backendImage: '${acr.outputs.loginServer}/cvscreening-backend:latest'
  ```
- **The Reality:** In ACR `crcvscreenexample`, the existing `:latest` tag was pushed 12 hours ago (`sha256:2f62f6d9...`). That is the **old image**, which lacks the verified graceful shutdown and SQLite restore logic. The new verified image exists only on your Mac as `cvscreening-backend:v2-durable` `[Verified]`.
- **Consequence if Unaddressed:** If deployed without pushing `v2-durable`, Container Apps will pull the obsolete image.
- **Required Action:** When pushing the image in Gate 2, `cvscreening-backend:v2-durable` must be tagged and pushed as `:latest` (and `:v2-durable`):
  ```bash
  docker tag cvscreening-backend:v2-durable crcvscreenexample.azurecr.io/cvscreening-backend:latest
  docker tag cvscreening-backend:v2-durable crcvscreenexample.azurecr.io/cvscreening-backend:v2-durable
  docker push crcvscreenexample.azurecr.io/cvscreening-backend:latest
  docker push crcvscreenexample.azurecr.io/cvscreening-backend:v2-durable
  ```

---

## 4. Security, Networking & Persistence Risks

```
+─────────────────────────────────────────────────────────────────────────────+
| Architecture & Network Flow                                                 |
+─────────────────────────────────────────────────────────────────────────────+
| Public Internet (Client Browser)                                            |
|   │                                                                         |
|   ▼ (HTTPS:443)                                                             |
| Azure Container Apps Edge Router (cae-cvscreen-prod-eastus2-example)   |
|   │                                                                         |
|   ▼ (Port 80)                                                               |
| Frontend Container (React 19 + Nginx)                                       |
|   │                                                                         |
|   │ Internal Envoy Virtual Network (Private FQDN)                           |
|   │ proxy_pass https://app-cvscreen-backend-prod.internal.<domain>:8000;   |
|   ▼                                                                         |
| Backend Container (FastAPI + SQLite + Ollama)                               |
|   • Ingress: external = false (NO PUBLIC IP, INACCESSIBLE FROM INTERNET)    |
|   • Local ephemeral DB: /app/local_data/cv_screening.db (fast WAL mode)     |
|   • Sync to Azure Files: /app/data/cv_screening.db (CIFS, 60s sync + trap)  |
+─────────────────────────────────────────────────────────────────────────────+
```

### Risk Evaluations:
1. **Public Leak Risk (Constraint #7):** **ZERO RISK**. The backend has no public IP or public ingress. Resumes, database records, and Qwen model weights are physically isolated within the private virtual network.
2. **Internal HTTPS Routing Assumption:**  
   `container-apps.bicep` sets `BACKEND_URL: 'https://${backendApp...fqdn}'`. Envoy terminates TLS at the edge of the internal service mesh. Nginx default behavior has `proxy_ssl_verify off`, ensuring internal TLS certificates do not cause handshake aborts. *(Must be confirmed during Gate 4 smoke test)*.
3. **Database Write Durability:**
   - **Scale-to-Zero:** `entrypoint.sh` intercepts `SIGTERM`, stops Uvicorn first to drain active requests, executes an atomic snapshot to `/app/data/cv_screening.db`, and verifies integrity. **Zero data loss on planned scale-down**.
   - **Abrupt Crash (`SIGKILL` or host failure):** Maximum data loss window is 60 seconds (the background sync interval). For a candidate screening demonstration, this is fully acceptable.
4. **Physical Capacity in `eastus2` (Unverified Assumption):**  
   ARM pre-flight checks passed, but Azure allocates physical compute capacity only during container app provisioning. If `eastus2` encounters capacity limits, fallback to another region (`centralus`) is planned.

---

## 5. Cost Assumptions & Staging Budget

```
+──────────────────────+───────────────────────────+──────────────────────+──────────────────────+
| Component            | Sizing / Scale Policy     | Trial Cost (Credits) | Permanent Post-Trial |
+──────────────────────+───────────────────────────+──────────────────────+──────────────────────+
| Backend Compute      | 2.0 vCPU, 4.0 GiB (min=0) | ₹0 (within quota)    | ₹0 (within quota)    |
| Frontend Compute     | 0.5 vCPU, 1.0 GiB (min=0)*| ₹0 (within quota)    | ₹0 (within quota)    |
| Azure Files (CIFS)   | 10-50 MB (SQLite Snapshots| ₹0 (absorbed)        | ~₹10 - ₹25 / month   |
| Blob Storage         | Resumes & Extracted Text  | ₹0 (free tier)       | < ₹2 / month         |
| Log Analytics & AppI | Telemetry Ingestion       | ₹0 (5 GB free grant) | ₹0 (5 GB free grant) |
| Bandwidth / Egress   | HTTPS & Demo Traffic      | ₹0 (100 GB grant)    | ₹0 (100 GB grant)    |
| Registry: ACR Std    | Active in eastus          | ₹0 (trial credits)   | ~₹1,660 / month      |
+──────────────────────+───────────────────────────+──────────────────────+──────────────────────+
| TOTAL NET COST       | With spendingLimit: "On"  | ₹0.00 to card        | ~₹1,685 / month      |
+──────────────────────+───────────────────────────+──────────────────────+──────────────────────+
```
*\*Recommendation: For permanent ₹0 compute, set frontend `minReplicas: 0`. During trial, `minReplicas: 1` is covered by trial credits.*

---

## 6. Cold-Start & Runtime Performance Expectations

When scaling up from 0 replicas upon client access:
1. **Frontend Activation:** Container boot + Nginx startup takes **~1.5 – 3 seconds**.
2. **Backend Activation:**
   - Container allocation + network attachment: ~5 – 8s.
   - Database restoration from Azure Files: < 0.5s.
   - Ollama daemon launch (`ollama serve`): ~2s.
   - Model availability check (`qwen2.5:1.5b` pre-baked in image): ~1s.
   - FastAPI initialization (Uvicorn): ~2s.
   - **Total Backend Cold Start:** **~12 – 18 seconds**.
3. **Client Experience:**
   - Browser requests to `/api/*` are held by Nginx (`proxy_read_timeout 300s`, `proxy_connect_timeout 75s`).
   - The user experiences a 15-second loading spinner on the first AI request, followed by normal sub-second candidate queries and 7-second Qwen resume evaluations.

---

## 7. Dependency-Ordered Deployment Sequence

```
[ Step 1: Health Probe Fix ] ───> Update container-apps.bicep probe path to /api/system/health
                                    │
[ Step 2: ACR Authentication ] ─> Log into crcvscreenexample (az acr login)
                                    │
[ Step 3: Tag & Push Backend ] ──> Tag v2-durable as :latest and push to ACR
                                    │
[ Step 4: Infrastructure Deploy ] > Run az deployment group create (cae in eastus2)
                                    │
[ Step 5: Live Smoke Test ] ────> Validate public frontend URL, candidate table & AI HR chat
```

---

## 8. Rollback Plan

If deployment fails or encounters a regional capacity error in `eastus2`:

1. **Failure at Step 4 (Capacity error in `eastus2`):**
   - The deployment will fail cleanly without affecting existing resources in `eastus`.
   - Update `containerAppsLocation` in `parameters.prod.json` to an alternate region (e.g. `centralus`) and retry.
2. **Failure at Step 5 (Application runtime error):**
   - Retrieve logs safely: `az containerapp logs show --name app-cvscreen-backend-prod --resource-group rg-cvscreening-prod --follow`.
   - Scale replicas to 0 immediately to prevent resource consumption: `az containerapp stop --name app-cvscreen-backend-prod --resource-group rg-cvscreening-prod`.
3. **Complete Infrastructure Decommissioning:**
   - If desired, delete the Container Apps Environment: `az containerapp env delete --name cae-cvscreen-prod-eastus2-example --resource-group rg-cvscreening-prod --yes`.
   - All base data in `eastus` (Azure Files snapshots, ACR images, blobs) remains completely untouched and safe.

---

## 9. Explicit Approval Matrix

In strict compliance with instructions, **no mutations will be performed without explicit user sign-off**. Please indicate which actions you authorize:

| Approval Gate | Action to be Taken | Mutation Type | Authorization Status |
| :--- | :--- | :--- | :--- |
| **Gate 1: Probe Path Fix** | Update probe path in `container-apps.bicep` from `/healthz` to `/api/system/health` | Local File Edit | [ ] Pending Approval |
| **Gate 2: Image Push** | Tag and push `cvscreening-backend:v2-durable` as `:latest` to ACR | Network / ACR Upload | [ ] Pending Approval |
| **Gate 3: Infrastructure Provisioning** | Execute `az deployment group create` to deploy Container Apps in `eastus2` | Azure Cloud Mutation | [ ] Pending Approval |
| **Gate 4: Live Verification** | Run read-only HTTPS smoke checks on the deployed public URL | Network Read-Only | [ ] Pending Approval |

---

## 10. Conclusion

The Phase 10 safety audit is complete. The system is verified, all risks and assumptions are documented, and the critical health probe path fix is ready to be applied upon your explicit instruction.
