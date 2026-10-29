# CVScreen: Cost Analysis, Cloud Economics & TCO Breakdown

**Document**: `COST_ANALYSIS_AND_ECONOMICS.md`  
**Purpose**: Complete financial analysis of CVScreen, covering Azure cloud infrastructure hosting costs, AI inference unit economics (Local SLM vs. OpenAI), and the permanent ₹0 / near-₹0 sustainability blueprint.

---

## 1. Executive Cost Summary

| Operating Phase | Monthly Cost (USD) | Monthly Cost (INR) | Primary Driver | Out-of-Pocket Status |
| :--- | :--- | :--- | :--- | :--- |
| **Current (30-Day Free Trial)** | **$0.00** | **₹0.00** | Covered by $200 (₹16,000) trial credits | **Hard Cap Enabled (₹0 billed)** |
| **Post-Trial (Unoptimized ACR Standard)** | ~$21.00 – $48.00 / mo | ~₹1,750 – ₹4,000 / mo | ACR Standard ($20/mo) + Frontend 24/7 idle | Billed to credit card |
| **Post-Trial (Optimized ₹0 Blueprint)** | **$0.00 – $0.40 / mo** | **₹0 – ₹35 / mo** | Docker Hub (Free) + Azure Files CIFS (<$0.40) | **Near-Zero / Permanent Free** |

---

## 2. Azure Infrastructure Sizing & Cost Breakdown

The table below lists every provisioned Azure resource in the production resource group (`rg-cvscreening-prod`), its tier, and billing mechanics:

| Azure Resource | Resource Name | SKU / Sizing | Monthly Cost (Retail) | Azure Free Grant / Rule | Net Trial Cost |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Azure Container Registry** | `crcvscreenexample` | Standard (100 GB) | $20.00 / mo (~₹1,660) | None for Standard | **₹0** (Trial credits) |
| **Container Apps Environment** | `cae-cvscreen-prod-eastus2` | Managed Consumption | $0.00 / mo (Base) | Included with Container Apps | **₹0** |
| **Backend Container App** | `app-cvscreen-backend-prod` | 2.0 vCPU / 4.0 GiB (`min: 0, max: 1`) | ~$0.00 – $35.00 / mo | 180,000 vCPU-s free/mo | **₹0** (Scales to 0) |
| **Frontend Container App** | `app-cvscreen-frontend-prod` | 0.5 vCPU / 1.0 GiB (`min: 1, max: 5`) | ~$0.00 – $12.00 / mo | Covered by 180k vCPU-s grant | **₹0** (Trial credits) |
| **Storage Account (Files/Blob)**| `stcvscreenprodxg4dry2ol` | Standard LRS (CIFS) | ~$0.30 / mo (~₹25) | 5 GB LRS free for 12 mos | **₹0** (Free tier) |
| **Log Analytics Workspace** | `law-cvscreen-prod` | Per-GB Ingestion | $0.00 / mo | 5 GB ingestion free/mo | **₹0** (Free tier) |
| **Application Insights** | `appi-cvscreen-prod` | Basic Telemetry | $0.00 / mo | Included in LAW grant | **₹0** (Free tier) |
| **Network Egress (Bandwidth)** | Internet Ingress/Egress | Standard Routing | $0.00 / mo | 100 GB egress free/mo | **₹0** (Free tier) |
| **TOTALS** | — | — | **~$20.30 – $67.30 / mo** | — | **₹0.00 billed** |

---

## 3. Azure Container Apps Free Allocation Rules

Azure Container Apps provides a generous **monthly recurring free grant** for every Azure subscription:

1. **180,000 vCPU-seconds free per month**:
   - Equivalent to **50 continuous hours** of 1.0 vCPU execution, or **25 hours** of 2.0 vCPU execution.
   - For an on-demand screening platform where each resume takes ~37 seconds of compute, 180,000 vCPU-seconds allows processing **~2,400 resumes every month for $0.00 in compute fees**.
2. **360,000 GiB-seconds free per month**:
   - Sufficient for memory allocations during active processing.
3. **2,000,000 HTTP requests free per month**:
   - Covers all health checks, dashboard refreshes, and API calls.

### Why Scale-to-Zero (`minReplicas: 0`) Is Critical
- In `app-cvscreen-backend-prod`, the container app is configured with `minReplicas: 0`.
- When recruiters are not actively uploading resumes or chatting, the container scales down to 0 replicas.
- **Result**: Zero vCPU-seconds are consumed while idle, conserving the monthly free allocation.

---

## 4. AI Inference Economics: Local SLM vs. Commercial APIs

A critical architectural differentiator of CVScreen is running a local Small Language Model (**Qwen 2.5 1.5B via Ollama**) instead of calling external proprietary APIs (such as OpenAI GPT-4o or Azure OpenAI).

### Unit Economics per 1,000 Resumes Processed

Assuming an average resume generates **2,500 prompt tokens** (CV text + system instructions + JSON schema) and produces **600 completion tokens** (structured candidate profile + timeline + skills):

| Inference Approach | Cost per 1M Input Tokens | Cost per 1M Output Tokens | Cost per Single Resume | Cost per 1,000 Resumes | Cost per 50,000 Resumes | Data Privacy Guarantee |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **OpenAI GPT-4o** | $2.50 | $10.00 | $0.0123 | **$12.30** (~₹1,020) | **$615.00** (~₹51,000) | Third-party cloud transmission |
| **Azure OpenAI GPT-4o-mini** | $0.15 | $0.60 | $0.0007 | **$0.74** (~₹61) | **$36.75** (~₹3,050) | Cloud compliance boundary |
| **CVScreen Local Qwen 2.5 (Ollama)** | **$0.00** | **$0.00** | **$0.00** | **$0.00** (~₹0) | **$0.00** (~₹0) | **100% Zero-Cloud Leakage** |

### Key Economic Takeaways:
1. **Zero Marginal Token Cost**: Whether CVScreen processes 10 resumes or 10,000 resumes, the token cost is strictly **$0.00**.
2. **Predictable Flat Infrastructure**: Operational costs do not scale linearly with hiring volume.
3. **Enterprise Compliance Savings**: Traditional enterprise AI parsers require expensive Business Associate Agreements (BAAs), SOC 2 type II certifications, and third-party data processing addendums. CVScreen's co-located model ensures candidate PII never leaves the private backend container boundary.

---

## 5. Post-Trial Sustainable ₹0 / Near-₹0 Migration Blueprint

When the 30-day Azure Free Trial ends, the subscription will transition to Pay-As-You-Go. To prevent charges while keeping the platform live, follow this 3-step blueprint:

### Step 1: Eliminate Azure Container Registry Standard ($20/mo)
- **Current State**: `crcvscreenexample` incurs ~$0.667/day ($20.00/mo).
- **Migration**:
  1. Create a free account on [Docker Hub](https://hub.docker.com/). Docker Hub provides **1 free private repository** indefinitely.
  2. Tag and push both images into a single private repository using different tags:
     - `docker.io/<username>/cvscreen:backend-latest`
     - `docker.io/<username>/cvscreen:frontend-latest`
  3. Update Container Apps to pull from Docker Hub using a Docker Personal Access Token (PAT).
  4. Run `az acr delete --name crcvscreenexample --resource-group rg-cvscreening-prod`.
  - **Net Savings**: **$20.00 / month (~₹1,660/mo) saved permanently**.

### Step 2: Set Frontend `minReplicas: 0`
- **Current State**: Frontend has `minReplicas: 1` to ensure instant page load. Running 24/7 consumes 1,314,000 vCPU-seconds per month, exceeding the free grant by ~1.1M vCPU-seconds ($27.20/mo).
- **Optimization**:
  - Run:
    ```bash
    az containerapp update --name app-cvscreen-frontend-prod \
      --resource-group rg-cvscreening-prod \
      --min-replicas 0
    ```
  - Both frontend and backend will scale to 0 when idle. The first visitor will experience a 5-second cold start, but hosting compute drops to **$0.00**.

### Step 3: Retain Azure Files for SQLite Persistence (< $0.40/mo)
- The Azure Storage Account (`stcvscreenprodxg4dry2ol`) with the `cvdatamount` CIFS share stores the SQLite database snapshot (~10–50 MB).
- Storage cost for $< 1\text{ GB}$ on Azure Files Standard is **~$0.06/GB/month** plus minimal transaction fees.
- **Total Persistent Storage Cost**: **~₹15 – ₹30 per month** (less than the cost of a cup of tea).
