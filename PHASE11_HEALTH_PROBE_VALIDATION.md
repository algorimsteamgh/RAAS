# Phase 11 — CVScreen Health Probe Fix and Final Validation Report

**Document:** `PHASE11_HEALTH_PROBE_VALIDATION.md`  
**Role:** Senior Azure DevOps Engineer & FastAPI Infrastructure Specialist  
**Date:** October 16, 2026  
**Status:** Health Probe Mismatch Resolved & Full ARM Pre-Flight Validated  
**Target Resource Group:** `rg-cvscreening-prod`  
**Scope:** `infra/bicep/modules/container-apps.bicep` only — Zero Azure mutations  

---

## 1. Executive Summary

In Phase 11, the critical deployment blocker identified in Phase 10—a mismatch between the backend Container App HTTP health probe paths (`/healthz`) and the actual FastAPI application route (`/api/system/health`)—was resolved.

The fix was applied exclusively to [`infra/bicep/modules/container-apps.bicep`](file:///Users/apple/cvscreening/infra/bicep/modules/container-apps.bicep). Zero application code, zero Dockerfiles, and zero application dependencies were modified. Both Bicep compilation (`az bicep build`) and Azure Resource Manager pre-flight validation (`az deployment group validate`) completed with **exit code 0 (`provisioningState: Succeeded`)**.

### Strict Safety & Compliance Attestation
- **Azure Resources Mutated:** **0** (No resources created, scaled, modified, or deleted).
- **Container Images Pushed:** **0** (`cvscreening-backend:v2-durable` remains exclusively local on the Mac host).
- **Deployments Executed:** **0** (`az deployment group create` was not run).
- **Public Accessibility:** **None** (Application is NOT deployed or publicly accessible).
- **Codebase Integrity:** Only `infra/bicep/modules/container-apps.bicep` was modified; all application code and configurations are preserved.

---

## 2. Health Endpoint Verification

Before making any infrastructure edits, the FastAPI route implementation was verified in [`backend/app/main.py`](file:///Users/apple/cvscreening/backend/app/main.py#L164-L189):

```python
# --- System Health ---
@app.get("/api/system/health")
async def system_health():
    import httpx
    ollama_status = "disconnected"
    ollama_model = settings.OLLAMA_LLM_MODEL
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            if res.status_code == 200:
                ollama_status = "connected"
                models = res.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                if not any(ollama_model in mn for mn in model_names):
                    ollama_status = "connected_model_missing"
    except Exception:
        ollama_status = "disconnected"

    return {
        "ollama_status": ollama_status,
        "ollama_model": ollama_model,
        "ollama_url": settings.OLLAMA_BASE_URL,
        "parser_status": "ready",
        "database_status": "ready",
        "version": "3.0.0"
    }
```

### Route Behavior & Probe Suitability:
1. **HTTP Method & Path:** `GET /api/system/health` `[Verified via route introspection]`.
2. **Authentication / Headers:** **None**. No bearer tokens, API keys, cookies, or headers required.
3. **HTTP Status Code:** Always returns **HTTP 200 OK** once Uvicorn is listening.
4. **Resilience under Cold Start:** The Ollama availability check is wrapped in a `try...except` block. Even while Ollama is starting up, the endpoint gracefully catches the timeout, sets `"ollama_status": "disconnected"`, and returns HTTP 200 OK. It **never throws an unhandled exception or returns a 5xx error**, making it reliable for Container Apps liveness and readiness evaluation.
5. **Absence of `/healthz`:** FastAPI route introspection confirmed that `/healthz` is not registered in the backend application. A probe to `/healthz` would have returned HTTP 404, triggering container termination after 5 probe cycles.

---

## 3. Configuration Change Applied

### File Modified
- [`infra/bicep/modules/container-apps.bicep`](file:///Users/apple/cvscreening/infra/bicep/modules/container-apps.bicep) (Lines 214–237)

### Exact Git Diff
```diff
--- a/infra/bicep/modules/container-apps.bicep
+++ b/infra/bicep/modules/container-apps.bicep
@@ -215,7 +215,7 @@
             {
               type: 'Liveness'
               httpGet: {
-                path: '/healthz'
+                path: '/api/system/health'
                 port: 8000
               }
               initialDelaySeconds: 20
@@ -225,7 +225,7 @@
             {
               type: 'Readiness'
               httpGet: {
-                path: '/healthz'
+                path: '/api/system/health'
                 port: 8000
               }
               initialDelaySeconds: 10
```

### Preserved Probe Parameters:
- **Port:** `8000` (FastAPI backend listening port).
- **Liveness:** `initialDelaySeconds: 20`, `periodSeconds: 30`, `timeoutSeconds: 5`, `failureThreshold: 5`.
- **Readiness:** `initialDelaySeconds: 10`, `periodSeconds: 15`, `timeoutSeconds: 5`, `failureThreshold: 5`.
- **Frontend Probe:** Preserved at `/healthz` on port 80 (served directly by Nginx with `return 200 "healthy\n"`).

---

## 4. Compilation & ARM Pre-Flight Validation Results

### 4.1. Bicep Template Compilation
```bash
az bicep build --file infra/bicep/main.bicep --outfile /dev/null
```
- **Exit Code:** `0`
- **Output:** Clean compilation. 4 informational linter warnings standard in Bicep child modules. Zero syntax errors, zero type errors.

### 4.2. Azure Resource Manager Pre-Flight Validation (Read-Only)
```bash
az deployment group validate \
  --resource-group rg-cvscreening-prod \
  --template-file infra/bicep/main.bicep \
  --parameters @infra/bicep/parameters.prod.json
```
- **Exit Code:** `0`
- **Provisioning State:** `Succeeded`
- **Error:** `null`
- **Validated Resources:**
  - `Microsoft.Storage/storageAccounts/stcvscreenexample` in `eastus` (preserved)
  - `Microsoft.ContainerRegistry/registries/crcvscreenexample` in `eastus` (preserved)
  - `Microsoft.OperationalInsights/workspaces/law-cvscreen-prod-example` in `eastus` (preserved)
  - `Microsoft.Insights/components/appi-cvscreen-prod-example` in `eastus` (preserved)
  - `Microsoft.Resources/deployments/containerAppsDeployment` targeting `eastus2` (validated)

---

## 5. Deployment Prerequisites Review

| Checklist Item | Current State | Verification Status |
| :--- | :--- | :--- |
| **Backend Image Local State** | `cvscreening-backend:v2-durable`<br>ID: `sha256:41a30b9ac2ff...`<br>Size: 2.55 GiB uncompressed / ~1.2 GB compressed | **VERIFIED:** Exists locally on Mac host. Has NOT been pushed to ACR or any registry. |
| **Frontend Image in ACR** | `crcvscreenexample.azurecr.io/cvscreening-frontend:latest`<br>Digest: `sha256:7b861ff9...` | **VERIFIED:** Matches local image ID `7b861ff9...` and Bicep reference. Ready for deployment. |
| **Backend Ingress Privacy** | `container-apps.bicep` sets `ingress.external = false` | **VERIFIED:** Backend is internal only; inaccessible from the public internet. |
| **SQLite Single-Writer Safety** | Backend `maxReplicas: 1`, `minReplicas: 0` | **VERIFIED:** Enforces single writer against persistent Azure Files CIFS volume. |
| **Container Apps Environment Location** | `eastus2` | **VERIFIED:** Decoupled parameter `containerAppsLocation = 'eastus2'` avoids `eastus` capacity limit. |
| **Physical Capacity in `eastus2`** | Template schema and quota validated | **UNVERIFIED:** Physical host allocation occurs only during container provisioning. |

---

## 6. Remaining Deployment Blockers

Only two operational gates remain before CVScreen is live:

1. **Gate 2: Container Image Push (Pending User Approval):**
   - The local backend image `cvscreening-backend:v2-durable` must be tagged as `:latest` and pushed to ACR:
     ```bash
     docker tag cvscreening-backend:v2-durable crcvscreenexample.azurecr.io/cvscreening-backend:latest
     docker push crcvscreenexample.azurecr.io/cvscreening-backend:latest
     ```
   - *Requires explicit user approval before network dispatch.*
2. **Gate 3: Azure Infrastructure Provisioning (Pending User Approval):**
   - Execute `az deployment group create` to deploy the Managed Environment and container apps in `eastus2`.
   - *Requires explicit user approval before cloud mutation.*

---

## 7. Rollback Plan

If you wish to revert this configuration edit:
1. Open [`infra/bicep/modules/container-apps.bicep`](file:///Users/apple/cvscreening/infra/bicep/modules/container-apps.bicep).
2. On line 218 and line 229, change `path: '/api/system/health'` back to `path: '/healthz'`.

---

## 8. Conclusion

Phase 11 is complete. The health probe mismatch has been resolved in the infrastructure template and validated against Azure Resource Manager. Zero Azure resources were mutated, no container images were pushed, and no deployments were executed.

Awaiting user instructions on Gate 2 (Image Push) and Gate 3 (Infrastructure Provisioning).
