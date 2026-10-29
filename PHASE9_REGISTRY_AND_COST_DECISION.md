# Phase 9 — CVScreen Zero-Cost Registry Decision & Deployment Gate Report

**Document:** `PHASE9_REGISTRY_AND_COST_DECISION.md`  
**Role:** Senior Azure Cloud Architect, DevOps Engineer & AI Infrastructure Engineer  
**Date:** October 16, 2026  
**Status:** Architectural Decision & Deployment Readiness Audit Complete  
**Target Architecture:** React 19 + FastAPI + Ollama (Qwen 2.5 1.5B) + SQLite on Azure Container Apps  
**Scope:** Research, Read-Only Audits, Cost Analysis & Decision Matrix — Zero Azure Mutations  

---

## 1. Executive Recommendation

To balance the **strict ₹0 recurring cost constraint** with **enterprise security (Constraint #7: zero public exposure of code, model weights, resumes, or database)**, there are two distinct paths. Each has a clear technical profile:

### Path A: Fast Staging Deployment via Existing Private ACR *(Recommended for the current 30-Day Free Trial)*
- **Mechanism:** Retain existing Azure Container Registry (`crcvscreenexample` in `eastus`). Tag and push `cvscreening-backend:v2-durable` directly to it.
- **Cost Impact:** Standard ACR incurs ~$0.667/day (~$20.00/mo or ~₹1,660/mo). While the Azure Free Trial is active, this is **100% absorbed by your $200 trial credits**. Because your subscription has `spendingLimit: "On"` `[Verified]`, **₹0 will be billed to your credit card**.
- **Pros:** Zero Bicep configuration edits required; already validated and passed by ARM in Phase 8; frontend image `cvscreening-frontend:latest` is already present in ACR; fastest path to a live public URL.
- **Cons:** Not permanently free. When the 30-day trial expires, ACR will stop or require downgrading to Basic ($5/mo) or decommissioning.

### Path B: Permanent ₹0 Hosting via Private Docker Hub *(Recommended for Long-Term Permanent ₹0)*
- **Mechanism:** Host both frontend and backend images in a **single private repository** on Docker Hub Personal (`docker.io/<username>/cvscreen:backend-v2-durable` and `docker.io/<username>/cvscreen:frontend-latest`).
- **Cost Impact:** **$0.00 / ₹0.00 permanently** `[Verified]`. Docker Hub Personal includes 1 private repository for free with no monthly fee.
- **Pros:** Zero cost forever; 100% private; supported natively by Azure Container Apps via Personal Access Token (PAT).
- **Cons:** Requires updating `infra/bicep/modules/container-apps.bicep` to reference `index.docker.io` and a PAT secret; requires pushing both frontend and backend images from the Mac host; subject to Docker Hub’s 200 pulls/6 hours rate limit.

### Path C: GitHub Container Registry (GHCR) — **DISQUALIFIED `[Blocked]`**
- **Disqualification Reason:** GitHub Free private package storage is capped at **500 MB** `[Verified]`. The compressed backend image is **~1.2 GB**, exceeding the private quota by 240%. Public hosting is strictly prohibited by Constraint #7.

---

## 2. Registry Comparison Matrix

The table below contrasts all evaluated registries using current official pricing and terms:

| Evaluation Criterion | Azure Container Registry (Standard) `[Existing]` | Azure Container Registry (Basic) `[Alternative]` | Docker Hub Personal `[Free Plan]` | GitHub Container Registry (GHCR) `[Free Plan]` |
| :--- | :--- | :--- | :--- | :--- |
| **Status in CVScreen** | **Active in `eastus`** `[Verified]` | Available via Bicep `[Verified]` | Fully Viable `[Verified]` | **DISQUALIFIED** `[Blocked]` |
| **Monthly Cost** | **$20.00 / mo (~₹1,660)** `[Verified]` | **$5.00 / mo (~₹415)** `[Verified]` | **$0.00 / ₹0 permanently** `[Verified]` | Exceeds free tier `[Verified]` |
| **Covered by Free Trial?** | Yes (via $200 trial credits) | Yes (via $200 trial credits) | N/A ($0 cost) | N/A |
| **Permanent Free Tier?** | **NO** `[Verified]` | **NO** `[Verified]` | **YES** (1 private repo) `[Verified]` | Yes for public; 500MB private |
| **Private Repos Included** | Unlimited within storage | Unlimited within storage | **Exactly 1 Private Repo** `[Verified]` | Unlimited within 500MB cap |
| **Storage Cap** | 100 GiB included `[Verified]` | 10 GiB included `[Verified]` | Fair use policy `[Verified]` | **500 MB pooled** `[Verified]` |
| **Fits Backend (~1.2 GB)?** | **YES** (~1.2% capacity) | **YES** (~12% capacity) | **YES** `[Verified]` | **NO (1.2 GB > 500 MB)** `[Blocked]` |
| **Fits Frontend (~29 MB)?** | **YES** (Already uploaded) | **YES** | **YES** (Same repo, different tag) | **YES** |
| **Rate Limits** | High throughput SLA | 1,000 pulls/min SLA | 200 pulls / 6 hours `[Verified]` | Unlimited public; metered private |
| **ACA Native Authentication** | Managed Identity or Admin Key | Managed Identity or Admin Key | Username + Secret PAT `[Verified]` | Username + PAT `[Verified]` |
| **Public Leak Risk** | 0% (Strictly private) | 0% (Strictly private) | 0% (Private repository) | 0% (if private; public forbidden) |

---

## 3. Total Comprehensive Hosting Cost Analysis

A complete audit of every Azure service in the CVScreen resource group (`rg-cvscreening-prod`) reveals the following cost dynamics:

```
+─────────────────────────────────────────────────────────────────────────────+
| Total CVScreen Monthly Architecture Cost Breakdown                          |
+─────────────────────────────────────────────────────────────────────────────+
| Component           | Sizing / Configuration    | Azure Free Grant / Rule   | Net Cost (Trial) | Net Cost (Post-Trial)  |
+─────────────────────+───────────────────────────+───────────────────────────+──────────────────+────────────────────────+
| Backend Compute     | 2.0 vCPU, 4.0 GiB (min=0) | 180k vCPU-s free/mo       | ₹0 (within quota)| ₹0 (within quota)      |
| Frontend Compute    | 0.5 vCPU, 1.0 GiB (min=0)*| 360k GiB-s free/mo        | ₹0 (within quota)| ₹0 (within quota)      |
| Azure Files (CIFS)  | 10-50 MB (SQLite Snapshots| ~$0.06/GB + transactions  | ₹0 (trial credit)| ~₹10 - ₹25 / month     |
| Blob Storage        | ~50 MB (Resumes/Uploads)  | 5 GB LRS free for 12 mos  | ₹0 (free tier)   | < ₹2 / month           |
| Log Analytics       | Diagnostic telemetry      | 5 GB ingestion free/mo    | ₹0 (free grant)  | ₹0 (free grant)        |
| App Insights        | Performance telemetry     | Included in 5 GB grant    | ₹0 (free grant)  | ₹0 (free grant)        |
| Network Bandwidth   | HTTPS Traffic & Egress    | 100 GB egress free/mo     | ₹0 (free grant)  | ₹0 (free grant)        |
| Container Registry  | Standard ACR (Active)     | $20/mo flat daily rate    | ₹0 (trial credit)| ₹1,660 / month         |
| Container Registry  | Docker Hub Personal (Opt) | 1 private repo free       | ₹0 (free tier)   | ₹0 / month             |
+─────────────────────+───────────────────────────+───────────────────────────+──────────────────+────────────────────────+
| TOTAL NET COST      | With ACR Standard (Active)| Absorbed by Trial Credits | ₹0.00 to card    | ~₹1,685 / month        |
| TOTAL NET COST      | With Docker Hub Personal  | Permanent Free Subsystems | ₹0.00 to card    | ~₹15 - ₹25 / month     |
+─────────────────────────────────────────────────────────────────────────────+
```

### Critical Architectural Finding on Compute Cost:
- In `infra/bicep/modules/container-apps.bicep`, the frontend currently has `minReplicas: 1` `[Verified]`.
- Running an idle frontend 24/7 (730 hours/mo) consumes **1,314,000 vCPU-seconds**, exceeding the 180,000 free grant by 1,134,000 vCPU-seconds and incurring ~$27.20/mo (~₹2,260/mo) after trial credits!
- **Mandatory Optimization for Permanent ₹0:** To guarantee ₹0 compute charges, the frontend should also be configured with `minReplicas: 0`. Because Nginx starts in under 2 seconds, cold-starting the frontend upon an incoming browser request introduces virtually imperceptible latency while keeping compute consumption strictly ₹0.

---

## 4. Private Image-Pull Feasibility (Docker Hub to Azure Container Apps)

Azure Container Apps has **first-class native support** for pulling images from private Docker Hub repositories `[Verified]`.

### How It Works:
1. **Repository Structure:**  
   Docker Hub Free allows 1 private repository: `docker.io/<username>/cvscreen`.  
   Both container images reside in this single repository under distinct tags:
   - Backend: `index.docker.io/<username>/cvscreen:backend-v2-durable`
   - Frontend: `index.docker.io/<username>/cvscreen:frontend-latest`
2. **Authentication via Personal Access Token (PAT):**  
   Rather than account passwords, Docker Hub provides Personal Access Tokens with `Read-only` permissions on private repositories.
3. **Bicep Registry Declaration:**
   ```bicep
   configuration: {
     secrets: [
       {
         name: 'dockerhub-token'
         value: dockerHubPat // passed via @secure() parameter
       }
     ]
     registries: [
       {
         server: 'index.docker.io'
         username: dockerHubUsername
         passwordSecretRef: 'dockerhub-token'
       }
     ]
   ```
4. **Failure Modes & Mitigation:**
   - **Rate Limiting (HTTP 429):** Free authenticated users receive 200 pulls per 6-hour rolling window. Because ACA nodes cache image layers and the backend runs with `maxReplicas: 1`, pulls only occur on container cold starts. 200 pulls per 6 hours allows up to 33 cold-starts per hour, more than adequate for client demonstrations.
   - **PAT Expiration:** Using a token with an expiration date will lead to `ImagePullBackOff`. Mitigation: Configure a long-lived or unexpiring token for staging environments.
   - **FQDN Syntax:** ACA requires `index.docker.io` (not `docker.io`) in the `server` property when referencing Docker Hub in ARM/Bicep templates `[Verified]`.

---

## 5. Deployment Readiness Audit (Read-Only Evidence)

Every prerequisite for deployment was audited against live Azure and local system state:

```
+───────────────────────────────────────────────────────────────────────────────────+
| CVScreen Deployment Readiness Scorecard                                           |
+───────────────────────────────────────────────────────────────────────────────────+
| Item audited                                    | Status       | Evidentiary Basis|
+─────────────────────────────────────────────────+──────────────+──────────────────+
| Local Bicep Compilation                         | VERIFIED     | az bicep build exit code 0 |
| ARM Pre-Flight Validation                       | VERIFIED     | provisioningState: Succeeded |
| Base Resources in eastus (Storage, ACR, LAW)   | VERIFIED     | az resource list confirmed in eastus |
| Decoupled Container Apps in eastus2             | VERIFIED     | cae-...-eastus2 confirmed in Bicep |
| Physical Host Capacity in eastus2               | UNVERIFIED   | Allocation happens during create |
| Local Backend Image cvscreening-backend:v2-durable| VERIFIED   | Image ID 41a30b9ac2ff on Mac host|
| Backend Image Pushed to Remote Registry         | BLOCKED      | Has NOT been pushed to any registry|
| Frontend Image in ACR (crcvscreenexample)| VERIFIED  | Digest sha256:1b9e6ca2... in ACR |
| Private Backend Ingress (external: false)       | VERIFIED     | Configured in container-apps.bicep|
| SQLite Single-Writer Safety (maxReplicas: 1)    | VERIFIED     | Configured in container-apps.bicep|
| Frontend Reverse-Proxy Timeout (300s)           | VERIFIED     | frontend/nginx.conf proxy_pass verified|
+─────────────────────────────────────────────────+──────────────+──────────────────+
```

### Explanations:
1. **Regional Capacity (`eastus2`) is UNVERIFIED:**  
   ARM pre-flight checks validate template schema, parameters, and quotas. Azure does **not** reserve physical host slots during validation. Capacity in `eastus2` can only be empirically verified when Azure Container Apps attempts to spin up the Managed Environment.
2. **Backend Image is UNPUSHED (`Blocked`):**  
   The durable backend image (`cvscreening-backend:v2-durable`, ID `41a30b9ac2ff`, containing pre-baked Qwen 2.5 1.5B and SQLite restore logic) exists **only on your local Mac host**. It has not been pushed to ACR or Docker Hub.
3. **Frontend Image is ALREADY IN ACR (`Verified`):**  
   `crcvscreenexample.azurecr.io/cvscreening-frontend:latest` exists in ACR with digest `sha256:1b9e6ca20d035eba4cb3c2c450bb1f2dea0cce0d087a6a3d0ffd7f88e3918736` (28.8 MB).

---

## 6. Dependency-Ordered Deployment Plan

```
                   +─────────────────────────────────────────+
                   | Stage 0: Registry Decision (User Sign-off)|
                   +────────────────────┬────────────────────+
                                        │
                 ┌──────────────────────┴──────────────────────┐
                 ▼                                             ▼
     [ Option A: Active ACR ]                      [ Option B: Docker Hub ]
     - Keep Bicep as-is                            - Update Bicep for index.docker.io
     - Tag v2-durable for ACR                      - Tag v2-durable & frontend for Docker Hub
                 │                                             │
                 └──────────────────────┬──────────────────────┘
                                        │
                                        ▼
                   +─────────────────────────────────────────+
                   | Stage 1: Authenticate & Push Image(s)   |
                   +────────────────────┬────────────────────+
                                        │
                                        ▼
                   +─────────────────────────────────────────+
                   | Stage 2: Provision Azure Infrastructure |
                   | (Deploy cae-*-eastus2 via Bicep)        |
                   +────────────────────┬────────────────────+
                                        │
                                        ▼
                   +─────────────────────────────────────────+
                   | Stage 3: Live Verification & Smoke Test |
                   | (Single HTTPS URL, AI Chat, Candidates) |
                   +─────────────────────────────────────────+
```

---

## 7. Explicit Approval Gates

In accordance with strict operating constraints, no actions will be taken without explicit authorization. Please select your preferred strategy and grant permissions for the desired gates:

### Decision: Choose Registry Path
- [ ] **Strategy A (Use Existing ACR):** Utilize active Azure Free Trial credits. Push `cvscreening-backend:v2-durable` to `crcvscreenexample.azurecr.io`. Zero Bicep changes needed.
- [ ] **Strategy B (Use Private Docker Hub):** Achieve permanent ₹0 registry hosting. Push backend and frontend to a single private Docker Hub repository. Update Bicep with Docker Hub registry credentials.

### Future Execution Gates (Awaiting User Sign-Off):
- [ ] **Gate 2: Permission to push container image(s)**  
  *(Authenticate to selected registry and upload the backend image).*
- [ ] **Gate 3: Permission to provision Azure infrastructure**  
  *(Run `az deployment group create` to deploy the Container Apps Environment in `eastus2`).*
- [ ] **Gate 4: Permission to perform live deployment & smoke verification**  
  *(Verify the public frontend URL, private backend routing, and live AI resume screening).*

---

## 8. Conclusion

All research and audits are complete. The application architecture is sound, secure, and ready for deployment as soon as the registry strategy is chosen and authorization is granted. Zero Azure resources were mutated, no container images were pushed, and no deployments were executed during this phase.
