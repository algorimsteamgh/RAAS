# CVScreen: Code Execution Flow & Call Tracing

**Document**: `CODE_EXECUTION_FLOW.md`  
**Purpose**: Line-by-line, function-by-function execution trace of real source code from client-side user events through internal Python services and back to the browser DOM.

---

## 1. Trace Overview: The Resume Upload & Evaluation Request

Below is the verified code execution trace for a recruiter uploading `john_doe_resume.pdf` to CVScreen.

```
React Component (App.tsx: handleFileUpload)
  │
  ├──> Fetch API (POST /api/upload-cv)
         │
         ├──> Nginx Reverse Proxy (nginx.conf: proxy_pass)
                │
                ├──> FastAPI Entry Point (main.py: upload_cv)
                       │
                       ├──> Magic Byte & Format Validation (main.py:326-340)
                       ├──> Duplicate Checker (db/database.py: check_duplicate_file)
                       ├──> Text Extraction Service (services/pdf_service.py: extract_text_from_bytes)
                       ├──> Archive Original Binary (db/database.py: save_original_file)
                       │
                       ├──> AI Extraction Agent (agents/cv_agent.py: extract_candidate)
                       │      │
                       │      ├──> Token Estimator (cv_agent.py: estimate_token_count)
                       │      ├──> Ollama Client (services/ollama_client.py: generate_json)
                       │      │      └──> HTTP POST http://127.0.0.1:11434/api/generate
                       │      │
                       │      ├──> JSON Parser & Sanitizer (ollama_client.py: _clean_and_parse_json)
                       │      ├──> Layout Reconciliation (cv_agent.py: _reconcile_employment_positions)
                       │      ├──> Grounding Engine (services/evidence_verifier.py: verify_and_ground_candidate)
                       │      └──> Interval Union Calculator (services/experience_calculator.py: calculate_total_experience_union)
                       │
                       ├──> SQLite Persistence (db/database.py: save_candidate_record)
                       └──> FastAPI Response Serialization (CandidateExtraction Pydantic Model)
                                │
                                └──> React UI Update (App.tsx: setSelectedCandidate & fetchEvidenceGraph)
```

---

## 2. Detailed Step-by-Step Code Walkthrough

### Phase 1: Client-Side Upload Trigger

1. **Source File**: `frontend/src/App.tsx`
   - **Function**: `handleFileUpload(files: FileList | File[])` (lines 620–680)
   - **Execution**:
     ```typescript
     const file = files[0];
     // Validation
     const validTypes = ['.pdf', '.docx', '.txt'];
     const hasValidExt = validTypes.some(ext => file.name.toLowerCase().endsWith(ext));
     if (!hasValidExt) {
       showToast('Please upload a PDF, DOCX, or TXT file', 'error');
       return;
     }
     
     // Set UI state to active progress
     setUploading(true);
     setUploadStage('reading');
     
     const formData = new FormData();
     formData.append('file', file);
     ```
2. **Network Call**:
   - `fetch(`${API_BASE}/api/upload-cv`, { method: 'POST', body: formData })`
   - Dispatches an asynchronous HTTP POST request to `/api/upload-cv`.

---

### Phase 2: Gateway & Reverse Proxy Routing

3. **Source File**: `frontend/nginx.conf`
   - **Block**: `location /api/` (lines 14–26)
   - **Execution**:
     ```nginx
     location /api/ {
         proxy_pass ${BACKEND_URL}; # In production: http://app-cvscreen-backend-prod.internal:8000
         proxy_http_version 1.1;
         proxy_set_header Host $proxy_host;
         proxy_set_header X-Real-IP $remote_addr;
         proxy_read_timeout 300s;
     }
     ```
   - Nginx preserves the multipart stream and proxies it over the internal container network to the backend port 8000.

---

### Phase 3: Controller Validation & Pre-Processing

4. **Source File**: `backend/app/main.py`
   - **Function**: `@app.post("/api/upload-cv") async def upload_cv(...)` (lines 318–397)
   - **Parameters Received**:
     - `file: UploadFile = File(...)`
     - `duplicate_action: Optional[str] = Query(None)`
   - **Step 4.1: Extension Check**:
     ```python
     ext = file.filename.split(".")[-1].lower()
     if ext not in ["pdf", "docx", "txt", "png", "jpg", "jpeg"]:
         raise HTTPException(status_code=400, detail="Unsupported file format.")
     ```
   - **Step 4.2: Read Content Bytes & Size Enforcement**:
     ```python
     content_bytes = await file.read()
     if len(content_bytes) > MAX_FILE_SIZE: # 10MB
         raise HTTPException(status_code=413, detail="File too large.")
     ```
   - **Step 4.3: PDF Magic Bytes Check**:
     ```python
     if ext == "pdf" and not content_bytes[:5].startswith(b'%PDF'):
         raise HTTPException(status_code=400, detail="Invalid PDF file.")
     ```
   - **Step 4.4: SHA-256 Hash & Duplicate Detection**:
     - Calls `db.calculate_sha256(content_bytes)` in `backend/app/db/database.py:476`:
       ```python
       return hashlib.sha256(content_bytes).hexdigest()
       ```
     - Calls `db.check_duplicate_file(sha256_hash)` in `backend/app/db/database.py:480`:
       ```python
       cursor.execute("SELECT candidate_id, filename FROM original_files WHERE sha256_hash = ?", (sha256_hash,))
       ```
     - If matched and `duplicate_action is None`: returns HTTP 409 JSON payload.

---

### Phase 4: Deterministic Text Extraction & File Archival

5. **Source File**: `backend/app/services/pdf_service.py`
   - **Function**: `PDFService.extract_text_from_bytes(file_bytes)` (lines 13–47)
   - **Execution**:
     ```python
     reader = pypdf.PdfReader(io.BytesIO(file_bytes))
     text_pages = [page.extract_text().strip() for page in reader.pages if page.extract_text()]
     full_text = "\n\n".join(text_pages).strip()
     if not full_text:
         raise PDFExtractionError("Could not extract readable text from PDF...")
     return full_text
     ```
6. **Archive Original Binary**:
   - `backend/app/db/database.py:save_original_file()` (lines 454–474):
     ```python
     conn.execute("""
         INSERT OR REPLACE INTO original_files (candidate_id, filename, file_type, sha256_hash, file_data)
         VALUES (?, ?, ?, ?, ?)
     """, (candidate_id, filename, file_type, sha256_hash, file_data))
     ```

---

### Phase 5: Autonomous AI Extraction & Verification

7. **Source File**: `backend/app/agents/cv_agent.py`
   - **Class**: `CVExtractionAgent`
   - **Method**: `async def extract_candidate(self, cv_text: str, candidate_id: str)` (lines 69–146)
   - **Step 7.1: Token Estimation**:
     ```python
     est_tokens = self.estimate_token_count(cv_text)
     if est_tokens <= SAFE_CONTEXT_TOKEN_LIMIT: # 3500 tokens
         raw_data = await self._extract_full_document(cv_text, candidate_id)
     else:
         raw_data = await self._extract_sequential_chunks(cv_text, candidate_id)
     ```
8. **Inference Invocation via OllamaClient**:
   - **Source File**: `backend/app/services/ollama_client.py`
   - **Method**: `async def generate_json(...)` (lines 16–52)
   - **Payload**:
     ```python
     payload = {
         "model": "qwen2.5:1.5b",
         "prompt": f"Extract structured data from this CV text:\n\n{cv_text}",
         "system": CV_EXTRACTION_SYSTEM_PROMPT,
         "stream": False,
         "format": "json",
         "options": {
             "temperature": 0.0,
             "num_predict": 1024,
             "num_thread": 2
         }
     }
     response = await client.post("http://127.0.0.1:11434/api/generate", json=payload)
     ```
   - **Sanitization**: `_clean_and_parse_json(raw_response)` (lines 88–119):
     - Uses regex to strip outer markdown ```` ```json ```` fences.
     - Locates outermost `{` and `}`.
     - Fixes trailing commas via `re.sub(r",\s*([\]}])", r"\1", text)`.

9. **Layout Reconcile & Ground Truth**:
   - `backend/app/services/document_layout.py`:
     `DocumentLayoutEngine.extract_structured_employment_records(cv_text)` extracts verified headers and company names.
   - `cv_agent.py:_reconcile_employment_positions()` matches LLM outputs against layout positions, discarding hallucinated bullet points.

10. **Deterministic Evidence Grounding**:
    - **Source File**: `backend/app/services/evidence_verifier.py`
    - **Method**: `EvidenceVerifier.verify_and_ground_candidate(raw_data, cv_text)` (lines 20–110)
    - **Execution**:
      ```python
      for skill in raw_data.get("skills", []):
          start_idx = cv_text.lower().find(skill.lower())
          if start_idx != -1:
              evidence_list.append(EvidenceItem(
                  attribute=f"skills:{skill}",
                  source_text=f"Found skill '{skill}' in CV",
                  verification_status=VerificationStatus.VERIFIED,
                  confidence=1.0,
                  char_offset_start=start_idx,
                  char_offset_end=start_idx + len(skill)
              ))
      ```

11. **Deterministic Timeline Union Calculation**:
    - **Source File**: `backend/app/services/experience_calculator.py`
    - **Method**: `ExperienceCalculator.calculate_total_experience_union(employment_history)` (lines 212–315)
    - **Execution**:
      - For each role: parses start and end dates via `DateNormalizer.normalize_to_iso()`.
      - Converts ranges into month indices: $[start\_idx, end\_idx]$.
      - Merges overlapping segments using boolean union array:
        ```python
        active_months = set()
        for s_idx, e_idx in non_internship_intervals:
            for m in range(s_idx, e_idx + 1):
                active_months.add(m)
        total_unique_months = len(active_months)
        ```
      - Prevents inflation when a candidate holds concurrent jobs.
      - Scans for gaps between consecutive roles $> 90$ days.

---

### Phase 6: Persistence & Delivery

12. **Source File**: `backend/app/db/database.py`
    - **Function**: `save_candidate_record(cand_data, source="UPLOADED", status="COMPLETED")` (lines 352–415)
    - **Execution**:
      ```python
      conn.execute("""
          INSERT OR REPLACE INTO candidates (
              candidate_id, full_name, email, phone, location,
              roles, skills, years_experience, notice_period,
              source, status, raw_json, file_hash, filename
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      """, (...))
      conn.commit()
      ```

13. **Controller Response**:
    - `main.py` returns serialized dictionary:
      ```python
      logger.info(f"Successfully processed {file.filename} in {time.time() - start_time:.2f}s")
      return cand_dict
      ```
    - Response traverses Nginx to browser.

---

### Phase 7: UI Update & Explainable Scoring

14. **Source File**: `frontend/src/App.tsx`
    - Handler receives HTTP 200 payload.
    - Updates local candidates array: `setCandidates(prev => [candDict, ...prev])`.
    - Selects new candidate: `setSelectedCandidate(candDict)`.
    - Fires secondary request for deep evaluation:
      `fetch(`${API_BASE}/api/candidates/${candDict.candidate_id}/evidence-graph`)`.

15. **Backend Evaluator Service**:
    - **Source File**: `backend/app/services/explainable_scorer.py`
    - **Method**: `ExplainableScorer.calculate_explainable_score(candidate, job_data)`
    - Computes 4-Pillar Score:
      ```python
      skill_score = (len(matched_skills) / len(required_skills)) * 40.0
      exp_score = min(1.0, verified_months / (required_years * 12)) * 25.0
      domain_score = (domain_overlap_ratio) * 20.0
      credibility_score = (verified_evidence_count / total_evidence_items) * 15.0
      overall = skill_score + exp_score + domain_score + credibility_score
      ```
    - Calls `InterviewEngine.generate_verification_questions()` to create dynamic technical and timeline probe questions.

16. **DOM Render**:
    - `<CandidateInspector />` renders candidate profile, score dials, timeline bars, and verified quotes.
