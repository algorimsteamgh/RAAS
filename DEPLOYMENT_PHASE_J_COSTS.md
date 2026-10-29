# Phase J — CVScreen Cost & Financial Analysis Report

**Timestamp:** 2026-10-16T12:32:00Z  
**Active Subscription:** Azure Free Trial (`FreeTrial_2014-09-01`)  
**Spending Limit:** Enabled (Hard Cap at ₹0 / $0 overage)  
**Target Resource Group:** `rg-cvscreening-prod`

---

## 1. Executive Summary

CVScreen is currently operating at **₹0 net out-of-pocket** because all provisioned services consume Azure Free Trial promotional credits and standard free-tier allowances. 

> [!WARNING]
> **No Permanent ₹0 Hosting Guarantee:** Azure does not offer an indefinitely free Standard Container Registry or 24/7 unmetered multi-core container compute. Once the 30-day Free Trial promotional credit window concludes, recurring charges will apply unless the migration steps outlined in this report are implemented.

---

## 2. Resource Inventory & Pricing Breakdown

| Azure Service | SKU / Tier | Allocation | Monthly Cost (USD) | Monthly Cost (INR) | Trial / Free Tier Coverage |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Azure Container Registry** (`crcvscreenexample`) | Standard | 100 GB storage | ~$20.00 / mo | ~₹1,660 / mo | Fully covered by ₹16,000 trial credits |
| **Azure Container Apps Managed Environment** (`cae-cvscreen-prod-eastus2-example`) | Consumption | 1 Environment (`eastus2`) | $0.00 / mo | ₹0 / mo | Included with Container Apps |
| **Backend Container App** (`app-cvscreen-backend-prod`) | Consumption | 2.0 vCPU / 4.0 GiB (`maxReplicas: 1`) | ~$0.00 - $35.00 / mo | ~₹0 - ₹2,900 / mo | Covered by 180k vCPU-s free grant + trial credits |
| **Frontend Container App** (`app-cvscreen-frontend-prod`) | Consumption | 0.5 vCPU / 1.0 GiB (`min: 1`, `max: 5`) | ~$0.00 - $12.00 / mo | ~₹0 - ₹1,000 / mo | Covered by 180k vCPU-s free grant + trial credits |
| **Azure Storage Account** (`stcvscreenexample`) | Standard LRS | Blob + Azure Files CIFS (< 5 GB) | ~$0.30 / mo | ~₹25 / mo | Covered by 5 GB LRS grant + trial credits |
| **Log Analytics Workspace** (`law-cvscreen-prod-example`) | Per-GB Ingestion | 5 GB/month free tier | $0.00 / mo | ₹0 / mo | 100% within free grant (< 100 MB/day) |
| **Application Insights** (`appi-cvscreen-prod-example`) | Basic | Shared with LAW | $0.00 / mo | ₹0 / mo | 100% within free grant |
| **Estimated Total Out-of-Pocket Today** | — | — | **$0.00** | **₹0.00** | **100% Credit Absorbed** |

---

## 3. Azure Container Apps Monthly Free Grant

Azure Container Apps provides the following monthly free allocation per Azure subscription:
- **180,000 vCPU-seconds** (~50 hours of continuous 1-vCPU execution, or hundreds of on-demand invocations).
- **360,000 GiB-seconds** of memory.
- **2,000,000 incoming HTTP requests**.

Because `app-cvscreen-backend-prod` is configured with `minReplicas: 0`, it scales to 0 when idle, maximizing the lifespan of the free tier and trial credits.

---

## 4. Post-Trial Sustainable Optimization Strategy

When the Azure Free Trial credits expire, the following zero-cost/near-zero-cost migration path is recommended:

1. **Migrate Container Images from ACR Standard to Docker Hub:**
   - Docker Hub provides 1 free private repository.
   - Decommissioning `crcvscreenexample` eliminates the **$20.00/mo (~₹1,660/mo)** recurring charge immediately.
2. **Preserve Azure Container Apps Consumption:**
   - Keep backend and frontend running on the Consumption tier with `minReplicas: 0` for development/staging workloads.
   - Incurred compute charges will only occur when active user traffic triggers container scaling.
3. **Retain Azure Storage:**
   - Azure Files and Blob storage costs for SQLite snapshots and resume PDFs are under **$0.50/mo (~₹40/mo)** for normal usage.
