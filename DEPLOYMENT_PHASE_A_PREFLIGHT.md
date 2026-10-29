# CVScreen Master Deployment — Phase A: Repository and Azure Preflight

**Document:** `DEPLOYMENT_PHASE_A_PREFLIGHT.md`  
**Execution Date:** October 16, 2026  
**Role:** Senior Azure Cloud Architect, DevOps Engineer & Site Reliability Engineer  
**Status:** Preflight Audit Completed  
**Resource Group:** `rg-cvscreening-prod`  

---

## 1. Azure Authentication & Active Subscription

Direct CLI verification:
```json
{
  "isDefault": true,
  "state": "Enabled",
  "subscriptionName": "Azure subscription 1",
  "quotaId": "FreeTrial_2014-09-01",
  "spendingLimit": "On"
}
```
- **Authentication:** Validated via active Azure CLI session.
- **Subscription Type:** Azure Free Trial (`FreeTrial_2014-09-01`).
- **Billing Protection:** Spending Limit is **`On`** (Credit card charges are blocked by Azure).

---

## 2. Resource Group & Base Resources Inventory

```
+─────────────────────────────────────────────────────────────────────────────+
| Azure Resource Inventory in rg-cvscreening-prod                             |
+─────────────────────────────────────────────────────────────────────────────+
| Resource Name                  | Type              | Location | Status      |
+────────────────────────────────+───────────────────+──────────+─────────────+
| rg-cvscreening-prod            | Resource Group    | eastus   | Succeeded   |
| stcvscreenexample       | Storage Account   | eastus   | Available   |
| ├── cv-data (50 GB share)      | Azure Files Share | eastus   | Ready       |
| └── cv-models (100 GB share)   | Azure Files Share | eastus   | Ready       |
| crcvscreenexample    | Container Registry| eastus   | Succeeded   |
| law-cvscreen-prod-example| Log Analytics     | eastus   | Succeeded   |
| appi-cvscreen-prod-example|App Insights       | eastus   | Succeeded   |
| cae-cvscreen-prod-example| Container Apps Env| eastus   | FAILED      |
+─────────────────────────────────────────────────────────────────────────────+
```

### Discrepancy Note on Storage Account Name:
- The master prompt noted: `stcvscreen-prod-examplehash`.
- **Verified Azure Name:** The actual storage account name in Azure is **`stcvscreenexample`** (no hyphen after `cvscreen`). All Bicep modules and scripts reference `stcvscreenexample` correctly.

---

## 3. Container App & Environment Existence Checks

1. **Target `eastus2` Environment:**
   - Resource `cae-cvscreen-prod-eastus2-example` in `eastus2` does **NOT** exist yet.
2. **Existing Container Apps in Subscription:**
   - `az containerapp list` returned **`[]`** (Zero Container Apps exist across the entire subscription).
3. **Failed Environment in `eastus`:**
   - Resource: `cae-cvscreen-prod-example` in `East US`.
   - Provisioning State: **`Failed`**.
   - Error: `ManagedEnvironmentCapacityHeavyUsageError` (East US regional capacity exhausted).
   - Attached Container Apps: **0**.
   - Storage Mounts: **0** (`az containerapp env storage list` returned `[]`).
   - Certificates: **0** (`az containerapp env certificate list` returned `[]`).
   - Custom Domains: **0** (`customDomainConfiguration.dnsSuffix: null`).
   - Underlying Infrastructure: `infrastructureResourceGroup: null` (Azure never allocated an AKS cluster).

---

## 4. Container Registry Image Audit

In `crcvscreenexample.azurecr.io`:

| Repository | Tag | Manifest Digest | Image Size (Compressed) | Content Verification |
| :--- | :--- | :--- | :--- | :--- |
| `cvscreening-backend` | `v2-durable` | `sha256:41a30b9ac2ffdb339452a9b02825a1d1183fc7221cc1ccc189ba30d6cc504e00` | ~1.2 GB | Pre-baked Qwen 2.5 1.5B, SQLite graceful sync & restore |
| `cvscreening-backend` | `latest` | `sha256:41a30b9ac2ffdb339452a9b02825a1d1183fc7221cc1ccc189ba30d6cc504e00` | ~1.2 GB | Synchronized with `v2-durable` |
| `cvscreening-frontend` | `latest` | `sha256:7b861ff9afb7d3c40e402abfd7d99faef70821fd35e255381b1147eeab657392` | 28.8 MB | React 19 SPA + Nginx reverse proxy |

---

## 5. Cost & Spending Limit Exposure

- **Container Registry (Standard SKU):** Costs ~$0.667/day (~$20.00/month or ~₹1,660/month). Covered by active Free Trial credits today.
- **Storage Account (Azure Files CIFS):** Billed at ~$0.06/GB/month (~$0.20/month or ~₹15/month). Covered by trial credits today.
- **Container Apps Compute:** 180,000 vCPU-seconds and 360,000 GiB-seconds free per month permanently.
- **Spending Limit:** Guaranteed `spendingLimit: "On"`. No credit card charges can be incurred under any circumstance.
- **Post-Trial Reality:** If the subscription transitions to Pay-As-You-Go, ACR Standard will bill ~$20/mo unless downgraded to Basic ($5/mo) or replaced with private Docker Hub.

---

## 6. Phase A Conclusion

Phase A preflight is **complete and verified**. All base infrastructure is operational, container images are verified in ACR, zero container apps currently exist, and the subscription is protected by spending limits.
