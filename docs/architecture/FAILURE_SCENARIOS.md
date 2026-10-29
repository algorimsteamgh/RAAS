# CVScreen: Failure Scenarios, Reliability Limits & Mitigations

**Document**: `FAILURE_SCENARIOS.md`  
**Purpose**: Production risk analysis covering compute constraints, AI inference edge cases, concurrency limitations, SQLite locking, and privacy guarantees.

---

## Risk Severity Matrix

| Risk / Failure Scenario | Nature of Risk | Severity | Primary Impact | Detection Method | Mitigation Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **CPU-Bound Inference Latency** | **Confirmed** | Medium | Uploads take 35–45s | Latency logging in `/api/upload-cv` | **Mitigated**: Token pruning + background upload pill |
| **Scale-to-Zero Cold Start** | **Confirmed** | Low | First request takes 15s | Liveness probe / container logs | **By Design**: Zero-cost Azure Consumption plan |
| **Scanned / Image-Only PDFs** | **Confirmed** | Medium | HTTP 422 Text Extraction Error | `PDFService` character count check | **Handled**: Explicit error returned to user |
| **Concurrent Write Locks in SQLite** | **Potential** | Medium | `sqlite3.OperationalError: locked` | Container error logs | **Mitigated**: WAL mode + single backend replica |
| **OOM Under Parallel Large Documents** | **Potential** | High | Container SIGKILL / crash | Azure Monitor Container Insights | **Mitigated**: 10MB file limit + 4GB container RAM |
| **Malformed LLM JSON Output** | **Potential** | Low | AI extraction failure | JSON parser exception | **Mitigated**: Regex sanitization & heuristic fallback |
| **Lack of Authentication (Single-Tenant)**| **Potential** | High | Publicly open candidate records | Security audit review | **Documented Constraint**: Internal prototype |

---

## 1. Slow AI Inference & Compute Limits

### Cause
Inference for Qwen 2.5 1.5B is computed entirely on **CPU cores** (2.0 vCPUs allocated to the backend container) rather than dedicated GPUs. Each generated token requires floating-point matrix multiplications over 1.5 billion parameters.
- Token generation throughput on 2 vCPUs: **~20–25 tokens/second**.
- If a resume prompt generates 1,000 tokens, compute time alone requires 40–50 seconds.

### Possible Impact
Recruiters uploading multiple resumes simultaneously may experience perceived freezes, and browsers could timeout if network timeouts are configured below 60 seconds.

### How to Detect It
- Search backend logs: `Processing upload for <file> in <time>s`.
- Timeouts will log HTTP 504 at the Nginx layer if exceeding `proxy_read_timeout 300s`.

### Practical Improvements
1. **Implemented**: Streamlined `CV_EXTRACTION_SYSTEM_PROMPT` to stop asking Ollama for verbatim quote arrays. Grounding is handled in Python in $<2\text{ms}$ by `EvidenceVerifier`. This reduced token output by 60%, dropping latency from 90s to ~37s.
2. **Implemented**: Added a **"Run in Background"** button and floating progress pill in the UI so recruiters can continue browsing while processing finishes.
3. **Future Production Option**: Switch Azure Container Apps to a GPU-enabled dedicated workload profile (`NC6s_v3` with NVIDIA Tesla V100), dropping inference to $<3$ seconds per resume.

---

## 2. Large Resume Uploads & Scanned PDFs

### Cause
1. Users may upload 20MB portfolio PDFs containing high-resolution graphics.
2. Users may upload scanned physical documents where pages are embedded JPEG images rather than selectable text.

### Possible Impact
- Large files consume container RAM and cause Uvicorn worker thread starvation.
- Scanned PDFs yield 0 selectable characters through `pypdf`.

### How to Detect It
- Scanned files trigger `PDFExtractionError("Could not extract readable text from PDF...")` in `PDFService.py:33`.
- Oversized files trigger HTTP 413 `File too large. Maximum size is 10MB.` in `main.py:336`.

### Practical Improvements
1. **Implemented**: Strict 10MB file size limit enforced before loading bytes into memory.
2. **Implemented**: Clean user-facing error toast explaining the PDF is scanned/encrypted.
3. **Future Production Option**: Integrate lightweight OCR (e.g. `tesseract` or Azure Computer Vision) into `PDFService` when `pypdf` extracts zero text characters.

---

## 3. SQLite Locking & Concurrency Limits

### Cause
SQLite uses database-level locking. While Write-Ahead Logging (WAL mode) allows unlimited concurrent readers, only **one writer** can commit a transaction at any given millisecond.

### Possible Impact
If 50 recruiters upload resumes simultaneously, concurrent threads attempting `INSERT INTO candidates` could encounter `sqlite3.OperationalError: database is locked`.

### How to Detect It
- Log searches for `database is locked` or `busy_timeout`.
- Spikes in response latency on write endpoints (`/api/upload-cv`, `/api/candidates/{id}/action`).

### Practical Improvements
1. **Implemented**:
   - `PRAGMA journal_mode=WAL;` enabled on every connection in `db/database.py:25`.
   - Backend Container App is scaled with `maxReplicas: 1` to prevent multiple container pods from fighting over the same file locks.
   - Database operations are wrapped with short transactional scopes and automatic connection closure.
2. **Future Production Option**: For enterprise deployments with $>50$ concurrent recruiters, migrate the persistence layer from SQLite to managed **Azure Database for PostgreSQL**. The domain service layer (`ExplainableScorer`, `ExperienceCalculator`, etc.) will require zero changes.

---

## 4. Missing or Malformed Model Output

### Cause
Small language models (1.5B parameters) running without external temperature constraints can occasionally emit non-compliant JSON:
- Wrapping JSON in conversational preamble: `"Here is the candidate JSON: ```json ..."`
- Trailing commas before closing brackets: `{"skills": ["Python", "SQL",]}`
- Hallucinated job titles based on resume bullet verbs.

### Possible Impact
FastAPI would raise an unhandled `json.JSONDecodeError`, aborting candidate extraction.

### How to Detect It
- Log warnings: `Failed to parse JSON directly from model response... Attempting basic sanitization`.

### Practical Improvements
1. **Implemented**: Multi-stage repair in `OllamaClient._clean_and_parse_json()`:
   - Regex-based markdown code fence stripper.
   - Substring isolation of the outermost curly braces `{ ... }`.
   - Regex repair of trailing commas.
2. **Implemented**: `DocumentLayoutEngine._reconcile_employment_positions()` validates candidate positions against layout-grounded ground truth, rejecting hallucinated bullet points.
3. **Implemented**: Deterministic heuristic fallback in `HRChatAgent` if Ollama returns an unparseable response.

---

## 5. Container Restarts & Persistence Failures

### Cause
Azure Container Apps periodically restarts containers during host maintenance or when scaling down to zero after idle periods.

### Possible Impact
If data were written exclusively to the container's ephemeral root filesystem, all uploaded candidate records, original files, and match results would be wiped on restart.

### How to Detect It
- Comparing candidate count before and after restart: `SELECT COUNT(*) FROM candidates`.
- Container restart logs in Azure Log Analytics: `ContainerInstanceTermination`.

### Practical Improvements
1. **Implemented**: Two-tier persistence with automated restore:
   - On boot, `entrypoint.sh` automatically restores `/app/data/cv_screening.db` from the durable Azure File Share.
   - Every 60 seconds, a background daemon flushes an online snapshot to `/app/data/cv_screening.db`.
   - A `SIGTERM` trap flushes the final database state before the container pod stops.
2. **Implemented**: Corrupted snapshots are quarantined with timestamped filenames to prevent overwriting recoverable records.

---

## 6. Authentication & Data Protection (Current State)

### Current Architecture
- CVScreen is currently deployed as an **internal prototype / proof-of-concept**.
- It does **not** implement user login, role-based access control (RBAC), or multi-tenant candidate isolation.
- Anyone with the public URL can browse candidates and upload CVs.

### Data Privacy Guarantees (Confirmed)
- **Zero Cloud Leakage**: Resume text is never sent to third-party AI APIs (OpenAI, Anthropic, Google).
- **Private Network Ingress**: The backend container has no public IP address and is strictly accessible via the frontend proxy.

### Recommended Next Steps for Enterprise Release
1. **Identity & Access Management**: Integrate **Microsoft Entra ID (Azure AD)** via EasyAuth or OAuth2/OIDC middleware in FastAPI to restrict access to authorized recruiters.
2. **PII Masking**: Add a recruiter toggle to mask Candidate Name, Email, and Phone during initial blind screening to eliminate hiring bias.
3. **Candidate Deletion API**: Implemented (`DELETE /api/candidates/{id}` and `DELETE /api/candidates/uploaded/all`) to support GDPR right-to-be-forgotten requests.
