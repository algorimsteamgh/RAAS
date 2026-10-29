# Phase G — CVScreen Backend Deployment Verification Report

**Timestamp:** 2026-10-16T12:07:30Z  
**Target Resource Group:** `rg-cvscreening-prod`  
**Container App:** `app-cvscreen-backend-prod`  
**Managed Environment:** `cae-cvscreen-prod-eastus2-example` (`eastus2`)

---

## 1. Executive Summary

The backend Container App `app-cvscreen-backend-prod` has been successfully provisioned and verified in `eastus2`. It is running with internal-only ingress, single-replica scale constraint to protect the SQLite database, persistent volume CIFS mounting at `/app/data`, and integrated Ollama + Qwen 2.5 1.5B daemon.

---

## 2. Configuration & Ingress Verification

| Parameter | Configured Value | Verification Status |
| :--- | :--- | :--- |
| **Provisioning State** | `Succeeded` | Verified (`az containerapp show`) |
| **Running Status** | `Running` | Verified |
| **Active Revisions Mode** | `Single` | Verified |
| **Ingress Scope** | `internal` (`ingressExternal: false`) | **Verified: NOT exposed to public internet** |
| **Internal FQDN** | `app-cvscreen-backend-prod.internal.braveglacier-819095d3.eastus2.azurecontainerapps.io` | Verified |
| **Target Port** | `8000` | Verified |
| **Min Replicas** | `0` | Verified |
| **Max Replicas** | `1` | **Verified: Strictly preserves SQLite single-writer safety** |

---

## 3. Storage Mount & Health Probes Verification

### Persistent CIFS Volume Mount
- **Volume Name:** `cv-storage-volume`
- **Managed Storage Target:** `cvdatamount` (mapped to Azure Files share `cv-data` on `stcvscreenexample`)
- **Container Mount Path:** `/app/data`
- **Status:** Successfully mounted and operational.

### Health Probes
- **Liveness Probe:**
  - Path: `/api/system/health`
  - Port: `8000`
  - Initial Delay: `20s`, Period: `30s`, Timeout: `5s`, Failure Threshold: `5`
  - Status: Passing (200 OK)
- **Readiness Probe:**
  - Path: `/api/system/health`
  - Port: `8000`
  - Initial Delay: `10s`, Period: `15s`, Timeout: `5s`, Failure Threshold: `5`
  - Status: Passing (200 OK)

---

## 4. Replica Startup & Ollama Engine Verification

Inspection of container logs from active replica `app-cvscreen-backend-prod--d11ijnm-ff68b9ff8-l8hdm`:
1. **Database Initialization:** Verified SQLite initialization at `/app/data/cv_screening.db` with 500 candidate profiles and 10 job descriptions.
2. **Ollama Daemon:** Ollama v0.40.5 started on `127.0.0.1:11434` with pre-baked model `qwen2.5:1.5b`.
3. **Uvicorn Server:** Running on `http://0.0.0.0:8000`.
4. **Health Route:** Recurring health checks returning `200 OK` with JSON telemetry.

---

## 5. Security & Isolation Gate

- [x] Backend is purely internal to the Container Apps environment virtual network.
- [x] No direct public ingress or external IP assigned to the backend.
- [x] Secrets and storage credentials securely stored in Container App environment secrets.
- [x] Backend image pinned to private ACR: `crcvscreenexample.azurecr.io/cvscreening-backend:latest`.
