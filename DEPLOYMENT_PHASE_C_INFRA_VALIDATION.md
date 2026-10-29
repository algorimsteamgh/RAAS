# CVScreen Master Deployment — Phase C: Infrastructure Review and Validation

**Document:** `DEPLOYMENT_PHASE_C_INFRA_VALIDATION.md`  
**Execution Date:** October 16, 2026  
**Role:** Senior Azure Cloud Architect & DevOps Engineer  
**Status:** Architecture Validated  

---

## 1. Templates Audited

1. [`infra/bicep/main.bicep`](file:///Users/apple/cvscreening/infra/bicep/main.bicep): Top-level orchestrator. Passes `location: 'eastus'` to base resources and `containerAppsLocation: 'eastus2'` to Container Apps.
2. [`infra/bicep/modules/container-apps.bicep`](file:///Users/apple/cvscreening/infra/bicep/modules/container-apps.bicep): Deploys the Managed Environment, CIFS CIFS storage mount, backend app, and frontend app.
3. [`infra/bicep/environment-only.bicep`](file:///Users/apple/cvscreening/infra/bicep/environment-only.bicep): Minimal, isolated template designed specifically for Step 7 (Gate 3). Deploys **only** `managedEnvironment` in `eastus2` without creating any container apps or modifying base infrastructure.

---

## 2. Invariant & Security Verification

| Invariant Checklist Item | Required Architectural Setting | Current Template Configuration | Status |
| :--- | :--- | :--- | :--- |
| **CAE Target Region** | `eastus2` | `containerAppsLocation = 'eastus2'` | **VERIFIED** |
| **Frontend Ingress** | Public HTTPS (`external: true`) | `frontendApp.properties.configuration.ingress.external = true` (Port 80) | **VERIFIED** |
| **Backend Ingress** | Internal only (`external: false`) | `backendApp.properties.configuration.ingress.external = false` (Port 8000) | **VERIFIED** |
| **SQLite Replica Safety** | `maxReplicas: 1` | `backendApp.template.scale.maxReplicas = 1`, `minReplicas = 0` | **VERIFIED** |
| **Persistent Mount Path** | `/app/data` (Azure Files CIFS) | `mountPath: '/app/data'`, `storageType: 'AzureFile'` | **VERIFIED** |
| **Backend Health Probes** | Valid FastAPI route (`/api/system/health`)| `liveness` and `readiness` both point to `path: '/api/system/health'` | **VERIFIED** |
| **Frontend Health Probe** | Valid Nginx route (`/healthz`) | `liveness` points to `path: '/healthz'` (Port 80) | **VERIFIED** |
| **Secret Management** | No embedded secrets | All secrets passed dynamically via `@secure()` ARM references | **VERIFIED** |

---

## 3. Template Compilation & ARM Pre-Flight Results

### 3.1. Compilation
```bash
az bicep build --file infra/bicep/main.bicep --outfile /dev/null
az bicep build --file infra/bicep/environment-only.bicep --outfile /dev/null
```
- **Exit Code:** `0` (Zero compilation errors).

### 3.2. ARM Pre-Flight Validation (`main.bicep`)
```bash
az deployment group validate \
  --resource-group rg-cvscreening-prod \
  --template-file infra/bicep/main.bicep \
  --parameters @infra/bicep/parameters.prod.json
```
- **Exit Code:** `0`
- **Provisioning State:** `Succeeded`
- **Error:** `null`

---

## 4. Phase C Conclusion

Infrastructure templates are verified, secure, and ready for deployment. The environment-only template is verified to contain zero application containers.
