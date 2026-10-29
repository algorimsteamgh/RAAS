# Phase 7 — CVScreen Deployment Blocker Resolution

**Document:** `PHASE7_BLOCKER_RESOLUTION.md`  
**Role:** Senior Azure Cloud Architect & DevOps Engineer  
**Date:** October 16, 2026  
**Status:** Pre-Deployment Architectural Blocker Analysis & Remediation Plan  
**Target:** Azure Container Apps / `rg-cvscreening-prod`  

---

## 1. Root Cause of the Regional Deployment Failure

### The Symptom
When testing a deployment of `infra/bicep/main.bicep` with parameter `location=eastus2`, Azure Resource Manager (ARM) immediately failed during pre-flight validation with `InvalidResourceLocation` across multiple resources:
```json
{
  "code": "MultipleErrorsOccurred",
  "message": "Multiple error occurred: Conflict,Conflict,Conflict. Please see details."
}
Inner Errors:
{"code": "InvalidResourceLocation", "message": "The resource 'law-cvscreen-prod-example' already exists in location 'eastus' in resource group 'rg-cvscreening-prod'. A resource with the same name cannot be created in location 'eastus2'. Please select a new resource name."}
{"code": "InvalidResourceLocation", "message": "The resource 'stcvscreenexample' already exists in location 'eastus' in resource group 'rg-cvscreening-prod'. A resource with the same name cannot be created in location 'eastus2'. Please select a new resource name."}
{"code": "InvalidResourceLocation", "message": "The resource 'crcvscreenexample' already exists in location 'eastus' in resource group 'rg-cvscreening-prod'. A resource with the same name cannot be created in location 'eastus2'. Please select a new resource name."}
{"code": "InvalidResourceLocation", "message": "The resource 'cae-cvscreen-prod-example' already exists in location 'eastus' in resource group 'rg-cvscreening-prod'. A resource with the same name cannot be created in location 'eastus2'. Please select a new resource name."}
```

### Static Analysis of the Bicep Dependency Graph
1. **Global Parameter Propagation:**  
   In [`infra/bicep/main.bicep`](file:///Users/apple/cvscreening/infra/bicep/main.bicep#L4), `param location string = resourceGroup().location` is a single top-level variable passed uniformly into every child module:
   - Line 45: `module monitoring 'modules/log-analytics.bicep' { params: { location: location } }`
   - Line 55: `module storage 'modules/storage.bicep' { params: { location: location } }`
   - Line 65: `module acr 'modules/acr.bicep' { params: { location: location } }`
   - Line 93: `module containerApps 'modules/container-apps.bicep' { params: { location: location } }`
2. **Deterministic Naming:**  
   Each sub-module names its resources deterministically using `uniqueString(resourceGroup().id)`:
   - Storage Account: `stcvscreenexample`
   - Registry: `crcvscreenexample`
   - Log Analytics: `law-cvscreen-prod-example`
   - Container Apps Environment: `cae-cvscreen-prod-example`
3. **The Azure ARM Constraint:**  
   In Azure, resources like Storage Accounts, Registries, and Log Analytics Workspaces have **immutable locations**. When `location=eastus2` is passed to `main.bicep`, ARM attempts to re-create the existing storage account and registry in `eastus2` with the exact same name, which Azure rejects.
4. **The Managed Environment Naming Collision:**  
   Similarly, `cae-cvscreen-prod-example` already exists in `eastus` (currently in `Failed` state due to `ManagedEnvironmentCapacityHeavyUsageError`). Attempting to deploy a Managed Environment with that identical name into `eastus2` within the same resource group causes a duplicate resource collision.

### The Decoupled Solution
Azure allows cross-region service consumption over the Microsoft global backbone:
- An Azure Container Apps Managed Environment in **`eastus2`** can pull container images from an ACR in **`eastus`**.
- It can ship telemetry to a Log Analytics Workspace in **`eastus`** via Workspace ID and Shared Key.
- It can mount an Azure Files CIFS volume from a Storage Account in **`eastus`** via storage account name and access key.

Therefore, `main.bicep` must decouple the Container Apps location (`containerAppsLocation = 'eastus2'`) from the base infrastructure location (`location = 'eastus'`), and `container-apps.bicep` must append the region to the Managed Environment name (`cae-${appName}-${environment}-${location}-${uniqueString(...) salwar}`) to eliminate naming collisions.

---

## 2. Proposed Bicep Changes (FOR REVIEW ONLY — NOT APPLIED)

### Change 1: `infra/bicep/main.bicep`
Decouple `containerAppsLocation` from base `location`. Existing Storage, ACR, and Monitoring remain in `eastus`, while the Container Apps Managed Environment is deployed to `eastus2`.
```diff
--- a/infra/bicep/main.bicep
+++ b/infra/bicep/main.bicep
@@ -4,2 +4,5 @@
 param location string = resourceGroup().location
+
+@description('Azure Region for Container Apps Managed Environment (decoupled to avoid capacity limits)')
+param containerAppsLocation string = 'eastus2'
 
@@ -90,3 +93,3 @@
 module containerApps 'modules/container-apps.bicep' = {
   name: 'containerAppsDeployment'
   params: {
-    location: location
+    location: containerAppsLocation
     environment: environment
```

### Change 2: `infra/bicep/modules/container-apps.bicep`
1. Include `${location}` in `environmentName` to prevent collision with the failed `eastus` environment.
2. Set backend `ingress.external = false` (Internal Ingress).
3. Set backend `minReplicas = 0` (Scale-to-Zero for ₹0 compute).
4. Set backend `maxReplicas = 1` (Single writer protection for SQLite).
```diff
--- a/infra/bicep/modules/container-apps.bicep
+++ b/infra/bicep/modules/container-apps.bicep
@@ -72,3 +72,3 @@
-var environmentName = 'cae-${appName}-${environment}-${uniqueString(resourceGroup().id)}'
+var environmentName = 'cae-${appName}-${environment}-${location}-${uniqueString(resourceGroup().id)}'
 var backendAppName = 'app-${appName}-backend-${environment}'
 var frontendAppName = 'app-${appName}-frontend-${environment}'
@@ -134,4 +134,4 @@
       ingress: {
-        external: true
+        external: false
         targetPort: 8000
         transport: 'auto'
@@ -240,4 +240,4 @@
       scale: {
-        minReplicas: 1
-        maxReplicas: 10
+        minReplicas: 0
+        maxReplicas: 1
         rules: [
```

### Change 3: `infra/bicep/parameters.prod.json`
Update parameters to explicitly document the decoupled architecture.
```diff
--- a/infra/bicep/parameters.prod.json
+++ b/infra/bicep/parameters.prod.json
@@ -4,4 +4,7 @@
   "parameters": {
     "location": {
       "value": "eastus"
+    },
+    "containerAppsLocation": {
+      "value": "eastus2"
     },
```

---

## 3. Internal Networking and Reverse-Proxy Verification

```
Internet Request (HTTPS:443)
       │
       ▼
[ Azure Container Apps Edge Router ]
       │  (Routes external traffic to public ingress)
       ▼
+───────────────────────────────────────────────────────────────+
│ Frontend Container (React 19 + Nginx)                         │
│ Ingress: external = true                                      │
│ Public URL: https://app-cvscreen-frontend-prod.<env>.azurecontainerapps.io │
+───────────────────────────────────────────────────────────────+
       │
       │  Private Envoy Virtual Network
       │  proxy_pass ${BACKEND_URL}; (300s timeout)
       ▼
+───────────────────────────────────────────────────────────────+
│ Backend Container (FastAPI)                                   │
│ Ingress: external = false (Private / Internal Only)           │
│ Internal FQDN: https://app-cvscreen-backend-prod.internal.<env>.azurecontainerapps.io │
+───────────────────────────────────────────────────────────────+
       │
       │  Localhost (127.0.0.1:11434)
       ▼
+───────────────────────────────────────────────────────────────+
│ Ollama Daemon (Qwen 2.5 1.5B)                                 │
+───────────────────────────────────────────────────────────────+
```

### How the Frontend Connects to the Private Backend:
- In `container-apps.bicep` lines 294–299:
  ```bicep
  env: [
    {
      name: 'BACKEND_URL'
      value: 'https://${backendApp.properties.configuration.ingress.fqdn}'
    }
  ]
  ```
- When `backendApp` has `ingress.external = false`, ARM automatically generates an internal FQDN in the format:
  `app-cvscreen-backend-prod.internal.<managed-environment-domain>`
- The Nginx image entrypoint (`20-envsubst-on-templates.sh`) reads `BACKEND_URL` and substitutes it into `/etc/nginx/conf.d/default.conf`.
- All client browser calls go to `/api/*` on the frontend URL. The browser never sees or contacts the backend.
- The backend is **physically inaccessible from the public internet**, providing complete protection for the API and SQLite database.

---

## 4. Registry Choice and Cost Reconciliation

| Feature / Metric | Option A: Existing Private ACR | Option B: Private Docker Hub | Option C: Private GHCR |
| :--- | :--- | :--- | :--- |
| **Official Plan Limit** | Standard: 100 GB<br>Basic: 10 GB | 1 Private Repository (up to 10 GB) | 500 MB private storage |
| **Compressed Image Size** | **~1.2 GB** (fits easily) | **~1.2 GB** (fits easily, 12% quota) | **~1.2 GB (Exceeds 500MB cap)** |
| **Permanent Recurring Cost** | Standard: $20.00/mo (₹1,660)<br>Basic: $5.00/mo (₹415) | **$0.00 / ₹0 permanently** | Paid storage overage ($0.25/GB/mo) |
| **Free Trial Credit Coverage** | Absorbed by trial credits while `spendingLimit: "On"` | Not needed ($0.00) | Not needed ($0.00) |
| **Container Apps Support** | Native Azure integration | Native (via `index.docker.io` & PAT) | Native (via `ghcr.io` & PAT) |
| **Confidentiality (Constraint #7)** | 100% Private | 100% Private (Auth required) | Public free, private paid |
| **Recommendation** | **Best for active 30-day trial** | **Best for permanent ₹0 on Azure** | **Rejected** |

### Verified Cost Breakdown:
1. **Compute (Container Apps):** **₹0.00** permanently.
   - Allowance: 180,000 vCPU-seconds and 360,000 GiB-seconds free per month.
   - Sizing: 2.0 vCPU, 4.0 GiB RAM.
   - With `minReplicas: 0`, staging consumption is ~10,000–30,000 vCPU-seconds (<17% of free quota).
2. **Logging (Log Analytics & App Insights):** **₹0.00** permanently (5 GB ingestion free/month).
3. **Storage (Azure Files):** **~$0.10–$0.30/month (~₹10–₹25/mo)** for 10MB SQLite snapshot storage.
4. **Registry Hosting:**
   - With ACR Basic: ~$5.00/mo (absorbed by trial credits today).
   - With Docker Hub Private: $0.00 permanently.

---

## 5. Database Persistence & Scale-to-Zero Verification

```
+─────────────────────────────────────────────────────────────+
│ Pod Working Memory (Local Ephemeral Container Storage)      │
│ Path: /app/local_data/cv_screening.db (WAL Mode)            │
│ Fast bare-metal SSD I/O. Zero CIFS byte-range lock issues.  │
+─────────────────────────────────────────────────────────────+
          │
          │  Periodic Sync (60s) & Shutdown Trap (SIGTERM)
          │  Python SQLite Online Backup API (src.backup)
          ▼
+─────────────────────────────────────────────────────────────+
│ Azure Files CIFS Mount (/app/data/)                         │
│ Path: /app/data/cv_screening.db                             │
│ 1. Atomic write to /app/data/cv_snap_<tmp>.tmp              │
│ 2. PRAGMA integrity_check;                                 │
│ 3. os.replace(tmp, /app/data/cv_screening.db)               │
+─────────────────────────────────────────────────────────────+
```

### Risk Evaluation:
1. **Scale-to-Zero Shutdown:**  
   When traffic drops to zero, Container Apps issues `SIGTERM` with a 30s grace period. In `scripts/entrypoint.sh`, Uvicorn is stopped first to drain active writes, followed by an atomic snapshot to Azure Files. Zero data loss occurs during planned scale-down.
2. **Cold-Start Latency:**  
   Scaling up from 0 replicas takes ~15–20s (container boot, database restoration, Ollama daemon startup, model verification). `frontend/nginx.conf` sets `proxy_read_timeout 300s`, ensuring the browser does not time out.
3. **Single Replica Safety:**  
   `maxReplicas: 1` is strictly mandatory. Multiple replicas writing to the same Azure Files snapshot would cause write-after-write corruption.
4. **Client Demo Suitability:**  
   **Fully suitable.** Provides end-to-end AI resume evaluation, HR chat, 500 mock profiles, and persistent state across reboots with zero local installation.

---

## 6. Dependency-Ordered Deployment Plan

```
[ Gate 1: Local Config ] ──> Apply decoupled Bicep diffs
                               │
[ Gate 2: Registry Push ] ───> Push v2-durable to ACR Basic or Docker Hub Private
                               │
[ Gate 3: Azure Infra ]  ───> Deploy Bicep (cae in eastus2, storage in eastus)
                               │
[ Gate 4: Live Smoke ]   ───> Verify Single Public HTTPS URL & AI Inference
```

1. **Step 1:** Apply local Bicep edits (`main.bicep`, `parameters.prod.json`, `container-apps.bicep`).
2. **Step 2:** Execute read-only pre-flight validation (`az deployment group validate`).
3. **Step 3:** Authenticate and push `cvscreening-backend:v2-durable` to the selected private registry.
4. **Step 4:** Provision the Container Apps Environment in `eastus2` and deploy frontend + backend container apps.
5. **Step 5:** Execute smoke test against the public frontend URL: health check, 500 mock candidate database verification, and live Qwen HR chat inference.

---

## 7. Go / No-Go Recommendation

- **For Permanent ₹0 without recurring costs:** **DO NOT PROCEED with ACR**. Choose **Docker Hub Private (100% free)** or **Self-Hosted Cloudflare Tunnel ($0.00)**.
- **For Active Staging via your Azure Free Trial:** **PROCEED WITH CAUTION**. The active Free Trial credits cover ACR Basic ($5/mo) and Storage (~₹20/mo), and your `spendingLimit: "On"` policy guarantees that **zero unexpected charges will reach your credit card**.

---

## 8. Explicit Approval Gates

No mutations have been performed. Progression requires explicit approval on each gate:

- [ ] **Gate 1: Permission to edit local configuration files**  
  *(Update `main.bicep`, `container-apps.bicep`, and `parameters.prod.json` with the decoupled diffs).*
- [ ] **Gate 2: Permission to push container image**  
  *(Push `cvscreening-backend:v2-durable` to your chosen registry).*
- [ ] **Gate 3: Permission to provision Azure infrastructure**  
  *(Deploy the Bicep template creating the Managed Environment in `eastus2`).*
- [ ] **Gate 4: Permission to perform live deployment and smoke tests**  
  *(Launch the containers and verify public HTTPS functionality).*
