# Phase 6 — CVScreen Deployment Preparation & Final Safety Gate

**Audit Date:** October 16, 2026  
**Auditor:** Senior Azure Cloud Architect, DevOps Engineer & Application Security Reviewer  
**Scope:** Pre-Deployment Verification, Cost Reconciliation, Security Audit, and Safety Gate  
**Target Environment:** Azure Container Apps / `rg-cvscreening-prod`  
**Application Stack:** React 19 + Nginx (Frontend), FastAPI (Backend), Pre-Baked Qwen 2.5 1.5B (Ollama), SQLite (Azure Files Sync)  

---

## 1. Executive Go / No-Go Verdict

### **Verdict: NO-GO for Permanent ₹0 on Native Azure; CONDITIONAL GO under Active Free Trial Credits or Private Docker Hub Distribution.**

| Evaluation Pillar | Status | Hard Architectural Reason |
| :--- | :---: | :--- |
| **Strict ₹0 Permanent Cost on Azure** | **NO-GO** | Azure Container Registry (ACR) has **no permanent free tier** ($5.00–$20.00/mo). While active Free Trial credits absorb this today with `spendingLimit: "On"`, the deployment will cease being ₹0 once trial credits lapse. |
| **Regional Compute Capacity** | **CONDITIONAL** | `eastus` is **definitively blocked** (`ManagedEnvironmentCapacityHeavyUsageError`). Pre-flight ARM validation confirms `eastus2` accepts the resource type, but physical cluster capacity in `eastus2` is **Unverified** until live provisioning. |
| **Workload Sizing & Inference** | **GO** | 2.0 vCPU / 4.0 GiB RAM runs Qwen2.5:1.5B with 1.8 GiB peak RSS and 7.65s CPU inference time. Fits within Container Apps monthly free compute grant (180,000 vCPU-seconds) when scaled to zero when idle. |
| **Data Protection & Persistence** | **GO** | Working DB on local ext4 container storage eliminates CIFS lock corruption. SQLite Online Backup API snapshots to Azure Files. Process-group `SIGKILL` tests proved crash durability and clean recovery. Single replica (`maxReplicas: 1`) prevents multi-writer corruption. |
| **Image Privacy & Security** | **GO** | Built image (`cvscreening-backend:v2-durable`, 2.55 GiB uncompressed / ~1.2 GB transfer) contains 0 PDF resumes, 0 databases, 0 credentials, and runs 100% offline with `--network none`. |

---

## 2. Verified vs. Unverified Findings Matrix

| Finding / Component | Status | Empirical Evidence / Citation |
| :--- | :---: | :--- |
| **Subscription Spending Guardrail** | **Verified** | `az rest` on subscription confirmed `quotaId: "FreeTrial_2014-09-01"` with **`spendingLimit: "On"`**. Azure cannot bill the credit card above trial allowance. |
| **Existing Resource State** | **Verified** | `rg-cvscreening-prod` holds active `Standard` ACR, Storage Account, Log Analytics, App Insights. Managed Environment `cae-cvscreen-prod-example` is in `Failed` state. |
| **Regional Capacity in `eastus`** | **Verified [BLOCKED]** | Azure returned `ManagedEnvironmentCapacityHeavyUsageError` on `cae-cvscreen-prod-example`. `eastus` is completely blocked. |
| **Regional Capacity in `eastus2`** | **Unverified** | ARM pre-flight validation accepted the template in `eastus2`, but Azure does not guarantee physical node allocation prior to deployment. |
| **Resource Name Collision in `eastus2`** | **Verified** | Re-deploying with `location=eastus2` using existing Bicep failed with `InvalidResourceLocation` because existing resources (`law*`, `st*`, `cr*`) are pinned to `eastus`. Bicep must decouple Managed Environment location or decouple modules. |
| **Model Offline Execution** | **Verified** | Docker container tested with `--network none`. Ollama initialized `qwen2.5:1.5b` and answered inference in 7.65s without internet access. |
| **Chat History Consistency** | **Verified** | Repeat test (`test_chat_discrepancy.py`) confirmed 1 chat interaction = exactly 2 DB records. Evaluated dictionary keys vs array length; row IDs and contents 100% identical across restarts. |
| **Candidate Seeding Deduplication** | **Verified** | Seeding logic checks `SELECT COUNT(*) FROM candidates` before seeding; candidate count stayed at exactly 500 across restarts. |
| **Image Layer Privacy** | **Verified** | Layer and rootfs scan revealed 0 real resumes, 0 databases, 0 `.env` files. Test suites and PII completely excluded by `.dockerignore`. |
| **Docker Hub Private Integration** | **Verified** | Container Apps Bicep schema natively supports `index.docker.io` via `configuration.registries` with username and PAT secret reference. |

---

## 3. Actual Cost Blockers Reconciled

To meet the user's **Strict ₹0 additional cost** constraint, we differentiate between **permanent free allowances** and **temporary promotional credits**:

```
Monthly Azure Cost Architecture:
+------------------------------------+--------------------------+-----------------------+
| Component                          | Free Grant / Allowance   | Commercial Cost       |
+------------------------------------+--------------------------+-----------------------+
| Container Apps Compute (Backend)   | 180,000 vCPU-s free/mo   | $0.00 (scale-to-zero) |
| Container Apps Compute (Frontend)  | Included in above pool   | $0.00 (scale-to-zero) |
| Log Analytics Ingestion            | 5 GB free per month      | $0.00 (staging < 0.2G)|
| Application Insights               | Linked to Log Analytics  | $0.00                 |
| Azure Files Storage & CIFS IO      | None permanent           | ~$0.10–$0.30/month    |
| Azure Container Registry (ACR)     | NO PERMANENT FREE TIER   | Standard: $20.00/mo   |
|                                    |                          | Basic:    $5.00/mo    |
+------------------------------------+--------------------------+-----------------------+
```

### The Blockers for Permanent ₹0:
1. **Azure Container Registry (ACR):**  
   Microsoft charges $0.667/day ($20/mo) for Standard and $0.167/day ($5/mo) for Basic. There is **no permanent free tier**. While the user's active Free Trial absorbs this right now (with `spendingLimit: "On"` preventing card charges), once trial credits lapse, ACR cannot be maintained for ₹0.
2. **Azure Files:**  
   Azure Files has no permanent free tier. Storing the 10MB database costs pennies (~₹10–₹25/mo), absorbed by trial credits, but strictly non-zero.
3. **GitHub Container Registry (GHCR) Infeasibility:**  
   GitHub Free provides only **500 MB** of private container storage. Our compressed image is **~1.2 GB**. Making the image public violates Constraint #7 (exposing proprietary code and weights). Therefore, GHCR cannot be used for ₹0.

### The True Zero-Cost Alternatives:
- **Alternative 1 (Azure Container Apps + Docker Hub Private Repo):**  
  Docker Hub provides **1 free private repository** up to 10 GB storage with private authenticated pulls. Container Apps pulls from Docker Hub using personal access token secrets. Deleting the ACR eliminates the recurring ACR fee, making the registry **permanently ₹0**.
- **Alternative 2 (Direct Host Run + Cloudflare Tunnel):**  
  Run `cvscreening-backend:v2-durable` on an existing Mac or server. Cloudflare Tunnel exposes a permanent public HTTPS URL (`https://cvscreen.<user-domain>.com`) with zero open ports, zero Azure hosting, and **100% permanent ₹0**.

---

## 4. Proposed Configuration Diffs (FOR REVIEW ONLY — NOT APPLIED)

The following diffs represent the exact technical changes required to achieve single-URL private backend routing, single SQLite writer safety, and regional deployment.

### Diff 1: `infra/bicep/parameters.prod.json`
*Targets `eastus2` to resolve the `eastus` capacity failure.*
```diff
--- a/infra/bicep/parameters.prod.json
+++ b/infra/bicep/parameters.prod.json
@@ -4,5 +4,5 @@
   "parameters": {
     "location": {
-      "value": "eastus"
+      "value": "eastus2"
     },
```

### Diff 2: `infra/bicep/modules/container-apps.bicep`
*Decouples environment name to prevent collision with failed `eastus` environment, enforces private backend ingress (`external: false`), sets `maxReplicas: 1` for SQLite, and sets `minReplicas: 0` for scale-to-zero compute savings.*
```diff
--- a/infra/bicep/modules/container-apps.bicep
+++ b/infra/bicep/modules/container-apps.bicep
@@ -72,3 +72,3 @@
-var environmentName = 'cae-${appName}-${environment}-${uniqueString(resourceGroup().id)}'
+var environmentName = 'cae-${appName}-${environment}-${location}-${uniqueString(resourceGroup().id)}'
 var backendAppName = 'app-${appName}-backend-${environment}'
 var frontendAppName = 'app-${appName}-frontend-${environment}'
@@ -134,3 +134,3 @@
       ingress: {
-        external: true
+        external: false
         targetPort: 8000
@@ -240,4 +240,4 @@
       scale: {
-        minReplicas: 1
-        maxReplicas: 10
+        minReplicas: 0
+        maxReplicas: 1
         rules: [
```

### Diff 3: `infra/bicep/modules/acr.bicep` (If Retaining ACR)
*Reduces ACR daily credit consumption by 75% ($5/mo vs $20/mo).*
```diff
--- a/infra/bicep/modules/acr.bicep
+++ b/infra/bicep/modules/acr.bicep
@@ -11,3 +11,3 @@
-param acrSku string = 'Standard'
+param acrSku string = 'Basic'
```

### Diff 4: `infra/bicep/main.bicep`
*Decouples existing `eastus` resources (Storage, ACR, Log Analytics) from the new Container Apps Environment location in `eastus2`.*
```diff
--- a/infra/bicep/main.bicep
+++ b/infra/bicep/main.bicep
@@ -4,2 +4,5 @@
 param location string = resourceGroup().location
+
+@description('Azure Region for Container Apps Managed Environment')
+param containerAppsLocation string = 'eastus2'
@@ -88,3 +91,3 @@
   params: {
-    location: location
+    location: containerAppsLocation
     environment: environment
```

---

## 5. Security & Persistence Review

### 1. Ingress Security & Single Public URL
- **Architecture:** The React 19/Nginx frontend is the **only public ingress point** (`ingress.external = true`).
- **Private Backend:** Setting `ingress.external = false` renders the FastAPI backend invisible to the public internet. It can only be called over the internal Container Apps virtual network by Nginx reverse proxying `/api/*`.
- **CORS Protection:** Because client browsers communicate strictly with the frontend origin over HTTPS, browser cross-origin restrictions (CORS) are completely bypassed.
- **Ollama Isolation:** The Ollama daemon binds to `127.0.0.1:11434` inside the backend container and is never exposed outside the pod.

### 2. Secrets, PII, and Layer Confidentiality
- **No Personal Resumes:** Tested and verified clean. Developer test suites (`backend/tests/`) and local database files (`*.db`) are excluded by `.dockerignore` and Dockerfile COPY constraints.
- **No Embedded Credentials:** Scanned entire rootfs for private keys, `.env` files, and credentials; zero found.
- **Masked Outputs:** Log outputs and status messages avoid printing sensitive tokens or connection strings.

### 3. SQLite Concurrency & Storage Lifecycle
- **Concurrency Protection:** Setting `maxReplicas: 1` guarantees that only one backend container instance can access the SQLite snapshot at any time, preventing CIFS lock conflicts.
- **Scale-to-Zero Durability:** When Container Apps scales down to 0 replicas during inactivity, it sends `SIGTERM` with a 30-second termination grace period. `scripts/entrypoint.sh` intercepts this signal, stops Uvicorn to complete in-flight writes, and takes a verified final backup snapshot to Azure Files before exiting.
- **Cold Start Impact:** Scaling from 0 to 1 replica takes ~20–30s. The Nginx reverse proxy is configured with `proxy_read_timeout 300s`, ensuring cold starts do not trigger HTTP 504 gateway timeouts.
- **Corrupted Snapshot Quarantine:** If an ungraceful crash occurs and an Azure Files snapshot fails `PRAGMA integrity_check;`, the entrypoint quarantines the damaged file to `cv_screening_corrupted_<timestamp>.db` and exits with code 1 instead of overwriting data.

---

## 6. Required Pre-Deployment Checks

Before authorizing any deployment, the following verification gates must pass:

1. **Regional Capacity Gate:** Perform a dry-run ARM deployment validation of the decoupled Bicep templates targeting `eastus2`.
2. **Registry Choice Gate:** Select between Path A (Existing ACR Basic via trial credit) or Path B (Docker Hub Free private repository).
3. **Image Tagging Gate:** Tag local image `cvscreening-backend:v2-durable` to the selected target registry.
4. **Volume Mount Sanity Gate:** Verify `stcvscreenexample` file share `cv-data` is accessible and empty.

---

## 7. Rollback & Disaster Recovery Plan

If any issue arises during or after deployment:

1. **Container Rollback (Zero Data Loss):**  
   Container revisions in Azure Container Apps are immutable. Rolling back to a previous revision or scaling down to 0 replicas does NOT touch the Azure Files share (`cv-data`).
2. **Database Recovery:**  
   The SQLite snapshot on Azure Files remains intact at `/app/data/cv_screening.db`. If a rollback container starts up, it validates and restores from this snapshot automatically.
3. **No Resource Group Deletion:**  
   Resource group `rg-cvscreening-prod` will never be deleted as a routine rollback. Individual container apps can be stopped with:
   `az containerapp stop --name app-cvscreen-backend-prod --resource-group rg-cvscreening-prod`
4. **Local Resilience:**  
   The local Docker image `cvscreening-backend:v2-durable` is fully verified on your Mac and can be launched locally at any time as an instant fallback.

---

## 8. Final Approval Checklist (Gated Boundaries)

The following distinct permissions are separated for explicit user authorization. **None have been executed.**

- [ ] **Gate 1: Permission to edit local configuration files**  
  *(Update `parameters.prod.json`, `main.bicep`, `container-apps.bicep`, and `acr.bicep` with the verified diffs).*
- [ ] **Gate 2: Permission to push container image to registry**  
  *(Push `v2-durable` to chosen registry: ACR Basic or private Docker Hub).*
- [ ] **Gate 3: Permission to provision Azure infrastructure**  
  *(Deploy the Bicep template creating the Managed Environment in `eastus2` and mounting Azure Files).*
- [ ] **Gate 4: Permission to deploy container applications and run live smoke tests**  
  *(Deploy backend and frontend Container Apps and verify the single public HTTPS URL).*

---

### Auditor Sign-Off
- **Azure Resources Mutated:** 0
- **Images Pushed:** 0
- **Infrastructure Deployed:** 0
- **Status:** **HALTED. Awaiting explicit user instruction on Gate 1.**
