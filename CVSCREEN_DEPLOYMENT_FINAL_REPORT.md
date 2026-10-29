# CVScreen — Production Deployment Final Report

**Date & Time:** October 16, 2026 — 18:02 IST (12:32 UTC)  
**Deployment Status:** **LIVE & FULLY VERIFIED**  
**Target Environment:** Azure Container Apps (`eastus2`)  
**Resource Group:** `rg-cvscreening-prod`  
**Subscription:** Azure Free Trial (`FreeTrial_2014-09-01`) — Spending Limit Active  

---

## 1. Verified Live Endpoints

| Service | Access Type | Live URL | Verified Status |
| :--- | :--- | :--- | :--- |
| **Frontend Web Application** | Public HTTPS | [https://app-cvscreen-frontend-prod.braveglacier-819095d3.eastus2.azurecontainerapps.io](https://app-cvscreen-frontend-prod.braveglacier-819095d3.eastus2.azurecontainerapps.io) | **200 OK (0.70s)** |
| **Backend REST API** | Private Virtual Network | `https://app-cvscreen-backend-prod.internal.braveglacier-819095d3.eastus2.azurecontainerapps.io` | **Internal Only (Enforced)** |
| **Telemetry Health Route** | Public (Proxied) | [https://app-cvscreen-frontend-prod.braveglacier-819095d3.eastus2.azurecontainerapps.io/api/system/health](https://app-cvscreen-frontend-prod.braveglacier-819095d3.eastus2.azurecontainerapps.io/api/system/health) | **200 OK (0.78s)** |

---

## 2. System Architecture & Components

```
                          [ Internet User / HR Recruiter ]
                                         │
                                         ▼ HTTPS (Port 443)
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ Azure Container Apps Managed Environment: cae-cvscreen-prod-eastus2-example       │
│ Region: eastus2                                                                        │
│                                                                                        │
│   ┌──────────────────────────────────────────────────────────────────────────────┐     │
│   │ app-cvscreen-frontend-prod (Public Ingress: port 80/443)                     │     │
│   │ - React 19 SPA (Production Build via Vite)                                   │     │
│   │ - Alpine Nginx Reverse Proxy with 300s Upstream Read Timeout                 │     │
│   │ - Image: crcvscreenexample.azurecr.io/cvscreening-frontend:v4      │     │
│   └──────────────────────┬───────────────────────────────────────────────────────┘     │
│                          │ Internal Envoy Overlay Network                              │
│                          │ HTTP http://app-cvscreen-backend-prod.internal...:8000      │
│                          ▼                                                             │
│   ┌──────────────────────────────────────────────────────────────────────────────┐     │
│   │ app-cvscreen-backend-prod (Internal Ingress: external=false)                 │     │
│   │ - FastAPI 3.0.0 Asynchronous Web Server (Uvicorn, Port 8000)                 │     │
│   │ - Local Ollama v0.40.5 Daemon (127.0.0.1:11434)                             │     │
│   │ - Model: Qwen 2.5 1.5B Instruct (Pre-baked in image, 0 external API cost)   │     │
│   │ - Scaling Constraint: minReplicas: 0, maxReplicas: 1 (Single-Writer SQLite)  │     │
│   │ - Image: crcvscreenexample.azurecr.io/cvscreening-backend:latest   │     │
│   └──────────────────────┬───────────────────────────────────────────────────────┘     │
│                          │ CIFS Mount /app/data                                        │
└──────────────────────────┼─────────────────────────────────────────────────────────────┘
                           ▼ SMB Protocol
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ Azure Storage Account: stcvscreenexample (Region: eastus)                       │
│ - Azure Files Share: cv-data (SQLite persistence snapshots, resumes, extracted data)   │
│ - Azure Files Share: cv-models (Model artifacts)                                       │
│ - Azure Blob Containers: cv-resumes, cv-extracted                                      │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. End-to-End Automated Verification Results

A 9-stage comprehensive automated integration test suite was executed against the live public URL:

1. **Frontend Assets (`GET /`):** HTTP 200 (HTML React root element validated).
2. **Nginx Liveness Probe (`GET /healthz`):** HTTP 200 (`healthy`).
3. **Backend Telemetry (`GET /api/system/health`):** HTTP 200 — Verified Ollama connected, Qwen 2.5 1.5B ready, SQLite ready.
4. **Dashboard Aggregations (`GET /api/dashboard/metrics`):** HTTP 200 — Verified 500 candidates and 10 jobs loaded from seed dataset.
5. **Job Catalog (`GET /api/jobs`):** HTTP 200 — 10 full job descriptions available.
6. **Candidate Directory (`GET /api/candidates?limit=3`):** HTTP 200 — Complete profile schemas returned.
7. **Deterministic Scoring Engine (`POST /api/match`):** HTTP 200 — Evaluated `CAND-0475` against `JOB-001` (Score 46.7, mandatory skill matching, experience scoring).
8. **On-Device LLM Inference (`POST /api/candidates/CAND-0475/chat`):** HTTP 200 in **8.23s** — Qwen 2.5 1.5B successfully summarized technical strengths with evidence and generated 4 follow-up interview questions.
9. **SQLite Action Persistence (`GET /api/candidates/CAND-0475/actions`):** HTTP 200 — Candidate shortlist decision recorded and persisted across reloads.

---

## 4. Key Engineering Interventions & Resolutions

1. **Global Subscription Quota Unlocked:**
   - Deleted the dead failed Container Apps Environment `cae-cvscreen-prod-example` in `eastus` (with explicit user authorization), releasing the subscription quota (0/1).
   - Successfully provisioned replacement environment `cae-cvscreen-prod-eastus2-example` in `eastus2`.
2. **Health Probe Contract Fixed:**
   - Corrected backend probe path from obsolete `/healthz` to actual FastAPI endpoint `/api/system/health` on port 8000, preventing container startup kill loops.
3. **Internal Reverse Proxy Header Routing:**
   - Identified that Nginx was passing incoming external Host header `$host` to the internal Envoy proxy, causing 404 routing mismatches. Updated Nginx configuration to forward `$proxy_host`, matching backend virtual routing.
4. **Internal Insecure Ingress Enablement:**
   - Enabled `allowInsecure: true` on backend internal ingress to prevent Envoy from redirecting internal HTTP cluster traffic to HTTPS on port 80.
5. **SQLite Single-Writer Protection:**
   - Enforced `maxReplicas: 1` on `app-cvscreen-backend-prod` to guarantee single-writer safety and eliminate SQLite database lock contention.

---

## 5. Cost Transparency & Sustainability

- **Current Status:** ₹0 net cost out-of-pocket (absorbed by ₹16,000 Azure Free Trial credits).
- **Trial Cap:** Azure spending limit is active, guaranteeing ₹0 unexpected billing.
- **Post-Trial Recurring Items:**
  - Azure Container Registry Standard: ~$20.00/mo (~₹1,660/mo). Recommended: Migrate to Docker Hub free tier.
  - Azure Container Apps Compute: Covered by monthly grant of 180,000 vCPU-seconds and scale-to-zero configuration.
  - Azure Storage Account: ~$0.30/mo (~₹25/mo).

---

## 6. Phase Reports Index

- [Phase A — Infrastructure & Registry Preflight](file:///Users/apple/cvscreening/DEPLOYMENT_PHASE_A_PREFLIGHT.md)
- [Phase B — Code Quality & Build Verification](file:///Users/apple/cvscreening/DEPLOYMENT_PHASE_B_QUALITY.md)
- [Phase C — Bicep Infrastructure Pre-Validation](file:///Users/apple/cvscreening/DEPLOYMENT_PHASE_C_INFRA_VALIDATION.md)
- [Phase D — Quota Resolution & Failed Environment Deletion](file:///Users/apple/cvscreening/DEPLOYMENT_PHASE_D_QUOTA_BLOCKER.md)
- [Phase E — Environment Provisioning](file:///Users/apple/cvscreening/DEPLOYMENT_PHASE_E_ENVIRONMENT.md)
- [Phase F — Container Registry Images Verification](file:///Users/apple/cvscreening/DEPLOYMENT_PHASE_F_IMAGES.md)
- [Phase G — Backend Container App Verification](file:///Users/apple/cvscreening/DEPLOYMENT_PHASE_G_BACKEND.md)
- [Phase H — Frontend Container App Verification](file:///Users/apple/cvscreening/DEPLOYMENT_PHASE_H_FRONTEND.md)
- [Phase I — Live Integration & Smoke Test Suite](file:///Users/apple/cvscreening/DEPLOYMENT_PHASE_I_SMOKE_TESTS.md)
- [Phase J — Financial Analysis & Cost Transparency](file:///Users/apple/cvscreening/DEPLOYMENT_PHASE_J_COSTS.md)
