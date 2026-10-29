# How CVScreen Works: End-to-End System Architecture & Execution Flow

**Document**: `HOW_CVSCREEN_WORKS.md`  
**Audience**: Software Engineers, Architects, Technical Mentors, Engineering Leads  
**Version**: 3.0.0 (Production Verified)  
**Repository**: `cvscreening`  

---

## 1. Executive Architecture Overview

CVScreen is an **evidence-based, zero-cloud candidate intelligence platform**. Unlike generic "black-box" AI resume parsers that feed an entire resume to a remote proprietary LLM and blindly trust the generated summary, CVScreen combines **local Small Language Model (SLM) structured extraction** with **deterministic Python algorithmic verification**.

Every candidate attribute extracted by the system (skills, dates, companies, degrees) is:
1. **Extracted privately** via a container-local instance of **Qwen 2.5 1.5B** running on **Ollama** (zero external API calls; zero candidate data leakage).
2. **Deterministically grounded** by verifying exact character offsets in the raw document via `EvidenceVerifier`.
3. **Mathematically deduplicated and timeline-normalized** via interval union algebra in `ExperienceCalculator` to prevent double-counting overlapping roles.
4. **Scored through a transparent, 4-pillar explainable framework** rather than a vague AI score.

---

## 2. The Complete End-to-End Workflow

The diagram and steps below trace the exact operational sequence when a recruiter opens the application, uploads a resume, and receives an auditable candidate evaluation.

```
+---------------+        HTTPS        +---------------------+        Proxy Pass        +----------------------+
|  Recruiter's  | ------------------> |   Frontend Pod      | -----------------------> |    Backend Pod       |
|    Browser    |                     | (Nginx + React SPA) |                          | (FastAPI + Uvicorn)  |
+---------------+                     +---------------------+                          +----------------------+
        |                                                                                         |
        | 1. GET /                                                                                |
        | 2. Loads Bundle (App.tsx)                                                              |
        | 3. Polls /api/system/health ----------------------------------------------------------> |
        |                                                                                         |
        | 4. User drops Resume (PDF/DOCX)                                                        |
        | 5. POST /api/upload-cv (Multipart Form) ----------------------------------------------> |
        |                                                                                         |
        |                                                                             6. Validates format & magic bytes
        |                                                                             7. Calculates SHA-256 & checks duplicates
        |                                                                             8. PDFService / DOCXService text extraction
        |                                                                             9. CVExtractionAgent (Ollama Qwen 2.5)
        |                                                                             10. DocumentLayoutEngine ground truth
        |                                                                             11. EvidenceVerifier exact offsets
        |                                                                             12. ExperienceCalculator interval union
        |                                                                             13. Saves original BLOB + JSON in SQLite
        |                                                                                         |
        | <-------------------------- Returns JSON CandidateExtraction ------------------------- |
        |                                                                                         |
        | 14. React selects Candidate & calls /api/candidates/{id}/evidence-graph -------------> |
        |                                                                             15. ExplainableScorer (4 Pillars)
        |                                                                             16. InterviewEngine (Targeted Qs)
        | <-------------------------- Returns 4-Pillar Score & Evidence ------------------------- |
        | 17. React renders Candidate Inspector, Verified Evidence Pills & Action Controls        |
```

---

### Step 1: User Opens the Application via Public HTTPS URL
- **Client Action**: Recruiter navigates to `https://app-cvscreen-frontend-prod.braveglacier-819095d3.eastus2.azurecontainerapps.io/`.
- **Infrastructure Path**:
  - The request hits the **Azure Container Apps Managed Environment Ingress**.
  - TLS is terminated at the Azure edge proxy using Microsoft's managed SSL certificates.
  - The ingress routes HTTP traffic on port 80 to the `frontend` container in the `app-cvscreen-frontend-prod` container app.

### Step 2: React Application Loads in the Browser
- **Nginx Serving**: Nginx receives `GET /` and serves static files from `/usr/share/nginx/html/` (built with Vite + TypeScript from `frontend/dist`).
- **Nginx Fallback**: If the user visits a deep link, `try_files $uri $uri/ /index.html;` ensures the React single-page application router handles navigation.
- **Client Initialization**:
  - `main.tsx` mounts `<App />`.
  - In `App.tsx` (`useEffect`), the client fires parallel initialization requests:
    - `GET /api/system/health`: Checks if the backend and local Ollama are healthy. Polled every 30 seconds to toggle the status indicator.
    - `GET /api/dashboard/metrics`: Fetches summary counts (total candidates, processed, pending).
    - `GET /api/candidates`: Populates the candidate sidebar list.
    - `GET /api/jobs`: Fetches available job descriptions.

### Step 3: User Interacts and Uploads a Resume
- **UI Trigger**: The user clicks the **"+ Upload"** button or drags a resume (`.pdf`, `.docx`, or `.txt`) into the drop-zone modal.
- **Client State**:
  - In `App.tsx` (`handleFileUpload`), the application validates client-side file properties (extension, size $\le 10\text{MB}$).
  - A `FormData` payload is prepared containing `file`.
  - The modal transitions into an animated multi-stage status view (`uploadStage: 'reading' | 'analyzing' | 'verifying'`).
  - Recruiters can optionally click **"Run in Background"**, which collapses the modal into a non-blocking header pill (`floating-progress-pill`) so they can continue reviewing other candidates without interruption.

### Step 4: Nginx Forwards the API Request to FastAPI
- **Proxy Configuration**: `frontend/nginx.conf`:
  ```nginx
  location /api/ {
      proxy_pass ${BACKEND_URL};
      proxy_http_version 1.1;
      proxy_read_timeout 300s;
      proxy_connect_timeout 75s;
  }
  ```
- **Internal Routing**:
  - `${BACKEND_URL}` resolves to `http://app-cvscreen-backend-prod.internal.braveglacier-819095d3.eastus2.azurecontainerapps.io:8000`.
  - The request stays entirely within the Azure Virtual Network / Managed Environment. No internal traffic is exposed to the public internet.

### Step 5: FastAPI Validates and Ingests the File
- **Handler**: `backend/app/main.py:upload_cv()` (`POST /api/upload-cv`).
- **Validation Pipeline**:
  1. **Filename & Extension**: Allowed formats: `.pdf`, `.docx`, `.txt`, `.png`, `.jpg`.
  2. **Size Enforcement**: `MAX_FILE_SIZE = 10 * 1024 * 1024` (10MB). Throws HTTP 413 if exceeded.
  3. **Magic Byte Verification**: For PDFs, validates `content_bytes[:5].startswith(b'%PDF')`. Throws HTTP 400 if malicious or renamed binary.
  4. **Cryptographic SHA-256**: Generates hash via `hashlib.sha256(content_bytes).hexdigest()`.
  5. **Duplicate Detection**: Queries SQLite `original_files` table via `db.check_duplicate_file(sha256_hash)`. If a duplicate exists and `duplicate_action` is not set, returns HTTP 409 Conflict with details of the existing candidate record. If `duplicate_action == 'replace'`, purges the previous record.
  6. **Unique Identifier**: Generates candidate ID `CAND-XXXXXXXX` using `uuid.uuid4()`.

### Step 6: Deterministic Text Extraction
- **Service Invocation**:
  - **PDFs**: Invokes `PDFService.extract_text_from_bytes(content_bytes)` (`backend/app/services/pdf_service.py`), which uses `pypdf.PdfReader` to extract clean page text streams.
  - **Word Documents**: Invokes `DOCXService.extract_text_from_bytes(content_bytes)` (`backend/app/services/docx_service.py`), iterating through XML paragraph blocks.
  - **Plain Text**: Decodes bytes directly using `utf-8` with fallback ignore.
- **Original File Archival**: Raw file bytes, filename, extension, and SHA-256 are stored in SQLite `original_files` table as a `BLOB` via `db.save_original_file()`. This enables recruiters to download or inspect the verbatim original file at any time via `/api/candidates/{id}/original-file`.

### Step 7: Backend Prepares Input and Sends Request to Ollama
- **Agent Invocation**: `cv_agent.extract_candidate(cv_text, candidate_id)` (`backend/app/agents/cv_agent.py`).
- **Token Estimation & Chunking Strategy**:
  - `estimate_token_count(cv_text)` checks length using subword heuristics.
  - **Under 3500 tokens**: Dispatches single-pass `_extract_full_document(cv_text)`.
  - **Over 3500 tokens**: Dispatches sequential state-aware chunking (`_extract_sequential_chunks`) with 2000-token windows and 250-token overlaps to avoid model context cutoff.
- **Ollama Request**:
  - `OllamaClient.generate_json()` sends an HTTP POST to `http://127.0.0.1:11434/api/generate`.
  - Payload parameters:
    - `"model": "qwen2.5:1.5b"`
    - `"format": "json"`
    - `"options": {"temperature": 0.0, "num_predict": 1024, "num_thread": 2}`
    - `"system": CV_EXTRACTION_SYSTEM_PROMPT`
    - `"prompt": f"Extract structured data from this CV text:\n\n{cv_text}"`

### Step 8: Ollama Runs Qwen 2.5 and Generates JSON
- **Execution**: The local C++ Ollama runtime processes the prompt against the pre-baked weights of Qwen 2.5 1.5B (loaded in container memory).
- **Concurrency**: Configured to utilize 2 CPU worker threads (`num_thread: 2`), utilizing the full 2.0 vCPU allocation of the backend container.
- **Output Constraint**: Constrained by the system prompt and Ollama grammar sampling to emit strict JSON without conversational chatter.

### Step 9: Backend Validates, Grounds, and Reconciles the Output
This is where CVScreen distinguishes itself from standard wrappers. Rather than trusting the LLM, the backend applies four layers of deterministic validation:

1. **JSON Sanitization & Repair**: `OllamaClient._clean_and_parse_json()` strips markdown code fences, isolates outer braces, and fixes trailing commas.
2. **Layout Ground Truth Reconcile**: `DocumentLayoutEngine` uses regex to extract genuine company names and date headers. `_reconcile_employment_positions()` discards LLM hallucinations (e.g., when the LLM mistakes a bullet point like "Developed REST APIs" for a company or job title).
3. **Deterministic Evidence Grounding**: `EvidenceVerifier.verify_and_ground_candidate(raw_data, cv_text)`:
   - For every extracted skill, degree, and title, it searches the raw document for exact substring matches.
   - Records exact `char_offset_start` and `char_offset_end` in the raw document.
   - Marks each claim as `VERIFIED` (found in document text) or `UNVERIFIED` (suspected hallucination).
4. **Deterministic Experience Calculation**: `ExperienceCalculator.calculate_total_experience_union()`:
   - Parses date strings into standard `YYYY-MM` ISO formats via `DateNormalizer`.
   - Performs interval union merging on overlapping date ranges (e.g., if Candidate worked at Company A from Jan 2020–Dec 2021 and Company B from Jun 2021–Dec 2022, they receive 36 months credit, not 42 months).
   - Segregates full-time professional experience from internships.
   - Flags concurrent employment overlaps and career gaps $> 3$ months.

### Step 10: Persistent Storage in SQLite
- **Database Connection**: `db.get_db_connection()` connects to `/app/local_data/cv_screening.db` with `PRAGMA journal_mode=WAL`.
- **Candidate Upsert**: `db.save_candidate_record()` writes the candidate record into the `candidates` table:
  - Columns: `candidate_id`, `full_name`, `email`, `phone`, `location`, `roles`, `skills`, `years_experience`, `notice_period`, `source`, `status`, `raw_json`, `file_hash`, `filename`.
- **Durable File Sync**: A background daemon in `entrypoint.sh` executes every 60 seconds, performing an online backup (`PRAGMA integrity_check` + SQLite Online Backup API) to `/app/data/cv_screening.db` on the mounted Azure Files share.

### Step 11: FastAPI Responds Through Nginx to Frontend
- FastAPI serializes the validated `CandidateExtraction` Pydantic model into JSON.
- Returns HTTP 200 to Nginx.
- Nginx streams the response back over HTTPS to the browser.
- Average processing duration: **~37 seconds** for warm inference.

### Step 12: React Displays the Candidate & Triggers Deep Evaluation
- **UI Update**:
  - The new candidate is prepended to the candidate list.
  - An animated toast appears: `"CV uploaded and processed successfully"`.
  - The candidate is automatically selected as the active candidate.
- **Deep Evaluation Trigger**:
  - When selected, `App.tsx` calls `GET /api/candidates/{candidate_id}/evidence-graph`.
  - The backend runs `ExplainableScorer.calculate_explainable_score(candidate, job_data)` to compute the **4-Pillar Score**:
    1. **Core Skills Match (40%)**: Ratio of required skills matched.
    2. **Experience Truth (25%)**: Ratio of verified non-overlapping months against required seniority.
    3. **Domain Relevance (20%)**: Alignment with target domain requirements.
    4. **Credibility & Evidence (15%)**: Ratio of claims verified with exact document character offsets.
  - `InterviewEngine.generate_verification_questions()` generates tailored interview questions targeting flagged career gaps, claimed experience discrepancies, and unverified skills.
  - The recruiter sees:
    - Overall score dial and recommendation (`Strong Match`, `Potential Match`, `Under-qualified`).
    - Grounded evidence pills with verbatim quotes from the resume.
    - Timeline view highlighting non-overlapping tenures and career gaps.
    - AI Verification Interview Questions.
    - Interactive **HR Chat** tab for asking specific follow-up questions.

---

## 3. Cost & Cloud Economics in the Workflow

A critical dimension of the CVScreen architecture is how each step in the workflow impacts hosting cost and token economics:

1. **In-Container Model Inference ($0 Token Cost)**:
   - Steps 7–9 run on the local container CPU via Ollama (`qwen2.5:1.5b`).
   - Unlike cloud APIs (OpenAI GPT-4o at ~$12.30 per 1,000 CVs), CVScreen incurs **$0.00 in per-token inference charges**.
2. **Serverless Scale-to-Zero Compute ($0 Idle Cost)**:
   - The backend Container App is configured with `minReplicas: 0`.
   - When no resumes are being processed, compute scales to zero, consuming none of the 180,000 vCPU-seconds monthly free grant.
3. **Durable Snapshot Persistence (< $0.40/mo)**:
   - The SQLite database is snapshotted to Azure Files (`cvdatamount`), which costs less than $0.40/month (~₹30/month) for normal usage.
4. **Current Status vs. Long-Term Free Tier**:
   - Currently, all resources (including the $20/mo Standard ACR) are 100% absorbed by the Azure Free Trial $200 promotional credits (hard spending cap set to ₹0).
   - Post-trial migration to Docker Hub Personal provides a permanent ₹0 to near-zero hosting environment.
   - For complete financial breakdowns, see [COST_ANALYSIS_AND_ECONOMICS.md](file:///Users/apple/cvscreening/docs/architecture/COST_ANALYSIS_AND_ECONOMICS.md).
