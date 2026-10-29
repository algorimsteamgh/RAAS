# Local AI CV Screening & Shortlisting Agent

> **100% Local • Zero Cloud APIs • Zero API Keys • Privacy First**  
> An AI-powered Resume/CV Screening, Evidence Extraction, Deterministic Scoring, and Evaluation Benchmark system powered by **Ollama**, **Qwen3 / Qwen3.5**, **FastAPI**, and **SQLite**.

---

## Key Features

- **Local AI Resume Parsing**: Extracts structured candidate profiles (contact details, skills, experience, education, evidence quotes, confidence scores, missing information alerts) using local Ollama (`qwen3:8b` or `qwen3.5:latest`).
- **Multi-Format Document Upload**: Ingests **PDF**, **DOCX**, **TXT**, and **Images** (`.png`, `.jpg`, `.jpeg`).
- **SHA-256 Duplicate Detection**: Automatically calculates SHA-256 hashes for uploaded resumes to prevent duplicates, prompting the recruiter with `[Skip]`, `[Replace]`, or `[Keep Both]`.
- **Deterministic Scoring Engine**: Calculates candidate match scores (0–100%) against Job Descriptions based on configurable weights:
  - **Mandatory Requirements**: 40%
  - **Technical Skills**: 25%
  - **Relevant Experience**: 20%
  - **Domain / Project Relevance**: 10%
  - **Preferred Skills**: 5%
  - Automatically assigns recommendation labels: `SHORTLIST` (≥75%), `REVIEW` (50%–74%), `DO_NOT_SHORTLIST` (<50%).
- **500-CV Synthetic Evaluation Benchmark**: Includes a built-in generator for 500 synthetic resumes, 10 Job Descriptions, and 5,000 ground-truth match annotations with varied resume quality (60% standard, 20% messy, 10% ambiguous, 10% edge cases).
- **`/evaluation` Benchmark Dashboard**: Developer/Admin page for computing **Skill Precision/Recall/F1**, **Matching Accuracy**, **Precision@5**, **NDCG@10**, and **Mean Reciprocal Rank (MRR)** against ground truth. Ground truth labels are strictly isolated from normal recruiter views.
- **Privacy & Audit Logging**: 100% local SQLite storage, document byte retrieval (`[ View Original Document ]`), individual candidate deletion, and bulk upload cleanup (`[ Delete All Uploaded ]`) with audit event logging.

---

## Tech Stack

- **LLM Engine**: Local [Ollama](https://ollama.com) (`qwen3.5:latest` or `qwen3:8b`)
- **Backend API**: Python 3.10+, FastAPI, Uvicorn, Pydantic v2
- **Document Extractors**: `pypdf`, `python-docx`
- **Database**: SQLite (`data/cv_screening.db`)
- **Frontend UI**: Vanilla JavaScript, Glassmorphism CSS design system, HTML5

---

## Prerequisites

1. **Python 3.10+** installed.
2. **Ollama** installed and running on `http://localhost:11434`.
   - Install Ollama from [ollama.com](https://ollama.com).

---

## Step-by-Step Installation & Setup Guide

### Step 1: Open Terminal & Navigate to Project
```bash
cd /path/to/cvscreening
```

### Step 2: Set Up Virtual Environment (Recommended)
```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Required Dependencies
```bash
python3 -m pip install fastapi uvicorn pydantic pypdf python-docx httpx python-multipart fpdf pillow
```

### Step 4: Start Ollama & Pull the Model
In a separate terminal window, start Ollama and pull your preferred model (e.g. `qwen3.5:latest` or `qwen3:8b`):
```bash
# Start Ollama service (if not running as a background service)
ollama serve

# In another terminal tab, pull the model
ollama pull qwen3.5:latest
```

### Step 5: Build 500-CV Synthetic Benchmark Dataset
Run the dataset builder to generate 500 synthetic resumes, 10 job descriptions, matching ground-truth records, and `dataset_manifest.json`:
```bash
python3 scripts/build_local_dataset.py
```

### Step 6: Start FastAPI Application Server
Launch the server on port 8000:
```bash
python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Accessing the Application

- **Web UI**: Open `http://localhost:8000` in your web browser.
- **API Swagger Docs**: Open `http://localhost:8000/docs`.

---

## Application Usage Guide

### 1. Resume Library (`http://localhost:8000`)
- **Filter Candidates**: Switch between `[All Sources]`, `[Mock (500)]`, and `[Uploaded]`.
- **Search**: Search candidates by name, role, or technical skill keyword.
- **Inspect Candidate**: Click any row to inspect candidate details, skill cloud, confidence meters, evidence quotes, and missing info alerts.
- **View Original File**: Click `[ View Original Document ]` to open/download the uploaded PDF/DOCX document.

### 2. Upload Resumes
- Click **`[ + Upload Resumes ]`**.
- Drag and drop single or multiple **PDF**, **DOCX**, **TXT**, or **Image** files.
- If a duplicate file is detected via SHA-256 hash, choose `[Skip]`, `[Replace]`, or `[Keep Both]`.
- Click `[ Upload & Process Queue ]`.

### 3. Match Candidate Against Job Description
- Select a candidate from the library and click **`[ 🎯 Match Against JD ]`**.
- Choose a target Job Description (e.g., *Senior Python Backend Engineer*, *React Frontend Engineer*).
- Click `[ Run Scoring Engine ]` to calculate composite score (%), matched skills, missing skills, and `SHORTLIST` / `REVIEW` / `DO_NOT_SHORTLIST` recommendation.

### 4. Benchmark `/evaluation` Dashboard
- Click **`/evaluation Dashboard`** in the top navigation.
- Click `[ Run Benchmark Evaluation ]`.
- View extraction metrics (**Skill Precision, Recall, F1**, **Experience Accuracy**) and matching metrics (**Accuracy**, **Precision@5**, **NDCG@10**, **MRR**).

---

## Running Automated Tests

Run the full pipeline unit test suite:
```bash
python3 -m unittest backend/tests/test_full_pipeline.py
python3 -m unittest backend/tests/test_pdf_upload_api.py
```

---

## Directory Structure

```
cvscreening/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI application server & endpoints
│   │   ├── config.py            # Project settings & Ollama URLs
│   │   ├── agents/
│   │   │   └── cv_agent.py      # Local Ollama CV Extraction Agent + Fallback
│   │   ├── db/
│   │   │   └── database.py      # SQLite database persistence & SHA-256 hash store
│   │   ├── schemas/
│   │   │   └── candidate.py     # Pydantic Candidate & Evidence schemas
│   │   ├── services/
│   │   │   ├── pdf_service.py   # PDF text extraction service (pypdf)
│   │   │   ├── docx_service.py  # DOCX text extraction service (python-docx)
│   │   │   ├── scoring_engine.py# Deterministic score & match engine
│   │   │   ├── evaluator.py     # Skill F1, NDCG@10, MRR benchmark evaluator
│   │   │   └── ollama_client.py # Local Ollama HTTP client
│   │   └── static/
│   │       ├── index.html       # Web UI Single Page Application
│   │       ├── style.css        # Glassmorphism dark mode stylesheet
│   │       └── app.js           # Client-side UI & event handlers
│   └── tests/
│       ├── test_full_pipeline.py# Full pipeline integration tests
│       ├── test_pdf_upload_api.py# PDF API upload unit tests
│       └── generate_sample_pdfs.py
├── scripts/
│   └── build_local_dataset.py   # 500-CV synthetic dataset generator
├── data/                        # Local SQLite DB, normalized data, & extracted JSONs
├── dataset/                     # 500 synthetic text resumes & ground truth JSONs
├── dataset_manifest.json        # Dataset provenance & statistics
└── README.md
```

---

## License & Privacy Statement

This software is designed for **100% local execution**. Candidate data, resumes, and extracted information are processed locally on your machine via Ollama and stored in a local SQLite database. **No resume content is ever sent to external cloud APIs or third-party servers.**
