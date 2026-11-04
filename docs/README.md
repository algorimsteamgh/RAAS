# Raashiring Enterprise AI Platform

> **Evidence-Based Candidate Intelligence • Deterministic Scoring • Privacy-First AI Architecture**  
> An enterprise AI-powered Resume Parsing, Evidence Extraction, Deterministic Matching, and Evaluation Benchmark platform powered by **React 18 + TypeScript**, **FastAPI**, **SQLite**, and **Ollama / Qwen (with Azure OpenAI enterprise connectors)**.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Frontend](https://img.shields.io/badge/Frontend-React%2018%20%7C%20TypeScript%20%7C%20Vite-61DAFB)](docs/FRONTEND.md)
[![Backend](https://img.shields.io/badge/Backend-FastAPI%20%7C%20Python%203.11-009688)](backend/)
[![Design](https://img.shields.io/badge/Theme-Corporate%20Blue-1E3E62)](frontend/src/index.css)
[![Cloud](https://img.shields.io/badge/Cloud-Azure%20Container%20Apps-0078D4)](docs/DEPLOY_NEW_AZURE_SUBSCRIPTION.md)

---

## Key Platform Features

- **Evidence-Backed AI Resume Parsing**: Extracts structured candidate profiles (contact details, verified skills, normalized experience timelines, education, and confidence meters) using local Small Language Models (SLMs) such as `qwen2.5:1.5b`, `qwen3.5`, or `qwen3:8b`.
- **Deterministic 4-Pillar Scoring Engine**: Eliminates LLM hallucination and score drift by computing mathematically verifiable candidate match scores (0–100%) against Job Descriptions:
  - **Mandatory Requirements**: 40%
  - **Technical Core Skills**: 25%
  - **Relevant Experience Depth**: 20%
  - **Domain / Project Relevance**: 10%
  - **Preferred Skills**: 5%
  - Automatically classifies candidates into actionable tiers: `SHORTLIST` (≥75%), `REVIEW` (50%–74%), and `DO_NOT_SHORTLIST` (<50%).
- **Multi-Format Ingestion with SHA-256 Deduplication**: Ingests **PDF**, **DOCX**, **TXT**, and **Images**. Computes SHA-256 cryptographic hashes on ingestion to detect duplicates, offering recruiters `[Skip]`, `[Replace]`, or `[Keep Both]`.
- **Executive Recruiter Dashboard**: Live KPIs tracking candidate pipelines, conversion ratios, average scores, and job distribution charts.
- **500-Candidate Synthetic Evaluation Benchmark**: Includes a built-in benchmark dataset generator with 500 synthetic resumes, 10 enterprise Job Descriptions, and 5,000 ground-truth annotations with varied document quality (standard, messy, ambiguous, edge cases).
- **Evaluation & Model Benchmarking Dashboard**: Computes **Skill Precision/Recall/F1**, **Matching Accuracy**, **Precision@5**, **NDCG@10**, and **Mean Reciprocal Rank (MRR)** against ground truth.
- **Privacy First & Enterprise Audit Logging**: Candidate resumes and extracted metadata remain strictly private. Runs 100% locally on premise or in private cloud containers without third-party vendor data leakage.

---

## Tech Stack

| Layer | Technologies |
| :--- | :--- |
| **Frontend UI** | React 18/19, TypeScript, Vite, Tailwind CSS, Lucide Icons, Plus Jakarta Sans & JetBrains Mono typography, Corporate Blue design system |
| **Backend REST API** | Python 3.10+, FastAPI, Uvicorn ASGI, Pydantic v2 |
| **AI / Inference Engine** | Local [Ollama](https://ollama.com) (`qwen2.5:1.5b`, `qwen3.5:latest`), with optional Azure OpenAI connectors |
| **Document Parsers** | `pypdf`, `python-docx`, Pillow, OCR extractors |
| **Database & Persistence** | SQLite 3 with Write-Ahead Logging (WAL) and Azure Files CIFS volume mounts |
| **Cloud Infrastructure** | Azure Container Apps (serverless scale-to-zero), Azure Container Registry, Azure Log Analytics, Bicep Infrastructure as Code |

---

## Architecture Overview

```
                                  [ Internet User / HR Recruiter ]
                                                 │
                                                 ▼ HTTPS (Port 443)
                      ┌─────────────────────────────────────────────────────┐
                      │    Azure Container Apps Ingress (Edge TLS Proxy)    │
                      └──────────────────────────┬──────────────────────────┘
                                                 │
                                                 ▼ (Port 80)
                      ┌─────────────────────────────────────────────────────┐
                      │             Frontend Web Application                │
                      │       (React 18 SPA + Vite + Nginx Reverse Proxy)   │
                      └──────────────────────────┬──────────────────────────┘
                                                 │
                                                 ▼ Proxy Pass /api/* (Port 8000)
                      ┌─────────────────────────────────────────────────────┐
                      │             Backend Application Pod                 │
                      │             FastAPI + Uvicorn + Pydantic v2         │
                      │                                                     │
                      │  ┌───────────────────────┐  ┌────────────────────┐  │
                      │  │   CV Extraction Agent │  │  Scoring Engine    │  │
                      │  │  (Ollama Qwen 2.5)    │  │  (4-Pillar Weights)│  │
                      │  └───────────────────────┘  └────────────────────┘  │
                      │  ┌───────────────────────┐  ┌────────────────────┐  │
                      │  │   Evidence Verifier   │  │ Experience Timeline│  │
                      │  └───────────────────────┘  └────────────────────┘  │
                      └──────────────────────────┬──────────────────────────┘
                                                 │
                                                 ▼ CIFS Mount / Local File
                      ┌─────────────────────────────────────────────────────┐
                      │     Persistent SQLite Database (WAL Mode)           │
                      │  Candidates • Match Results • Audit Events • Hashes │
                      └─────────────────────────────────────────────────────┘
```

---

## Quick Start & Local Setup

### 1. Prerequisites
- **Python 3.10+**
- **Node.js 18+** & **npm**
- **Ollama** installed from [ollama.com](https://ollama.com)

### 2. Pull the AI Model
```bash
ollama serve
ollama pull qwen2.5:1.5b
```

### 3. Start Backend Server
```bash
# Set up Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install backend dependencies
pip install -r requirements.txt # or: pip install fastapi uvicorn pydantic pypdf python-docx httpx python-multipart

# Initialize database and launch FastAPI server
python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Start Frontend Application
```bash
cd frontend
npm install
npm run dev
```

Open your browser at `http://localhost:5173` (or `http://localhost:8000` for backend Swagger API documentation at `/docs`).

---

## Production Cloud Deployment (Azure)

Deploy the full stack to Azure Container Apps with automated zero-cost scale-to-zero compute:

```bash
# Log in to Azure CLI
az login

# Set your target Azure region and run the deploy script
AZURE_LOCATION=eastus ./deploy-azure.sh
```

For complete instructions on deploying to a new subscription, see [`docs/DEPLOY_NEW_AZURE_SUBSCRIPTION.md`](./DEPLOY_NEW_AZURE_SUBSCRIPTION.md).

---

## Project Directory Structure

```
.
├── backend/                     # FastAPI backend application
│   ├── app/
│   │   ├── main.py              # Application entry point, endpoints, and startup lifespan
│   │   ├── config.py            # Platform settings and Ollama configuration
│   │   ├── agents/              # CV extraction and HR agent logic
│   │   ├── db/database.py       # SQLite database persistence and schema
│   │   ├── schemas/             # Pydantic v2 candidate & match schemas
│   │   └── services/            # Scoring engine, PDF/DOCX extractors, evaluator
│   └── tests/                   # Backend unit and integration test suite
├── frontend/                    # Modern React 18 TypeScript application
│   ├── src/                     # App.tsx, Corporate Blue CSS, and UI components
│   ├── public/                  # Brand assets, favicons, logos
│   ├── nginx.conf               # Production Nginx reverse proxy configuration
│   └── package.json             # Frontend dependencies and build scripts
├── infra/                       # Infrastructure as Code (Bicep)
│   └── bicep/                   # Container Apps, Storage, ACR, and Monitoring modules
├── scripts/                     # Automation scripts (dataset generator, Azure bootstrap)
├── docs/                        # Complete project documentation and phase reports
│   ├── README.md                # Primary platform documentation (this file)
│   ├── FRONTEND.md              # Frontend architecture and UI components guide
│   ├── DEPLOY_NEW_AZURE_SUBSCRIPTION.md # Azure deployment guide
│   ├── CVSCREEN_DEPLOYMENT_FINAL_REPORT.md # Production verification report
│   ├── architecture/            # Detailed technical architecture manuals
│   └── DEPLOYMENT_PHASE_*.md    # Operational deployment phase logs (A through J)
├── data/                        # Local SQLite DB and uploaded document storage
└── dataset/                     # Synthetic 500-candidate benchmark dataset
```

---

## Documentation Index

All architectural manuals, phase checklists, and deployment reports are located in the [`docs/`](./) directory:

### Architecture Guides
- [End-to-End System Architecture (`HOW_CVSCREEN_WORKS.md`)](./architecture/HOW_CVSCREEN_WORKS.md)
- [Complete Architecture & C4 Diagrams (`ARCHITECTURE_DIAGRAMS.md`)](./architecture/ARCHITECTURE_DIAGRAMS.md)
- [Code Execution Flow (`CODE_EXECUTION_FLOW.md`)](./architecture/CODE_EXECUTION_FLOW.md)
- [Azure Deployment Flow (`AZURE_DEPLOYMENT_FLOW.md`)](./architecture/AZURE_DEPLOYMENT_FLOW.md)
- [Design Patterns in Code (`DESIGN_PATTERNS_IN_CODE.md`)](./architecture/DESIGN_PATTERNS_IN_CODE.md)
- [Cost Analysis & Economics (`COST_ANALYSIS_AND_ECONOMICS.md`)](./architecture/COST_ANALYSIS_AND_ECONOMICS.md)
- [Failure Scenarios & Mitigation (`FAILURE_SCENARIOS.md`)](./architecture/FAILURE_SCENARIOS.md)

### Deployment & Verification Reports
- [Production Deployment Final Report](./CVSCREEN_DEPLOYMENT_FINAL_REPORT.md)
- [Azure Subscription Setup Guide](./DEPLOY_NEW_AZURE_SUBSCRIPTION.md)
- [Phase A — Preflight Audit](./DEPLOYMENT_PHASE_A_PREFLIGHT.md)
- [Phase B — Code Quality Verification](./DEPLOYMENT_PHASE_B_QUALITY.md)
- [Phase C — Infrastructure Pre-Validation](./DEPLOYMENT_PHASE_C_INFRA_VALIDATION.md)
- [Phase D — Quota & Blocker Resolution](./DEPLOYMENT_PHASE_D_QUOTA_BLOCKER.md)
- [Phase E — Environment Provisioning](./DEPLOYMENT_PHASE_E_ENVIRONMENT.md)
- [Phase F — Container Images Verification](./DEPLOYMENT_PHASE_F_IMAGES.md)
- [Phase G — Backend Container Verification](./DEPLOYMENT_PHASE_G_BACKEND.md)
- [Phase H — Frontend Container Verification](./DEPLOYMENT_PHASE_H_FRONTEND.md)
- [Phase I — Smoke Tests & Integration](./DEPLOYMENT_PHASE_I_SMOKE_TESTS.md)
- [Phase J — Cost Transparency & Optimization](./DEPLOYMENT_PHASE_J_COSTS.md)
- [Phase 10 — Final Pre-Deployment Safety Checklist](./PHASE10_FINAL_DEPLOYMENT_CHECKLIST.md)
- [Phase 11 — Health Probe Validation](./PHASE11_HEALTH_PROBE_VALIDATION.md)
- [Phase 13 — Infrastructure Provisioning Report](./PHASE13_INFRASTRUCTURE_PROVISIONING_REPORT.md)
- [Phase 14 — Environment Safety Review](./PHASE14_FAILED_ENVIRONMENT_SAFETY_REVIEW.md)

---

## License & Data Privacy

This platform is engineered for **100% privacy and data sovereignty**. Resumes, personal candidate details, and AI extraction workflows are processed locally or within your dedicated private virtual network. **No candidate data is ever transferred to third-party consumer LLM APIs.**
