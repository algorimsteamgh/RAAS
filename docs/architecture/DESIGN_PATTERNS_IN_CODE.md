# CVScreen: Design Patterns in Code — Reality vs. Aspiration

**Document**: `DESIGN_PATTERNS_IN_CODE.md`  
**Purpose**: Rigorous architectural audit identifying software design patterns actually implemented in the CVScreen codebase versus patterns that are merely future recommendations.

---

## Pattern Implementation Summary Matrix

| Pattern | Status in Codebase | Primary Implementation Location | Architectural Purpose |
| :--- | :--- | :--- | :--- |
| **Layered Architecture** | **REAL** | `frontend/`, `backend/app/{api,agents,services,db}` | Strict separation of UI, routing, domain AI, algorithms, and SQL |
| **Service Layer** | **REAL** | `backend/app/services/*.py` | Encapsulates reusable business algorithms without HTTP awareness |
| **Repository Pattern** | **REAL (Functional)** | `backend/app/db/database.py` | Centralizes SQLite queries; lacks abstract interface class |
| **Adapter Pattern** | **REAL** | `backend/app/services/ollama_client.py` | Adapts raw Ollama HTTP API into strongly-typed JSON/Text engine |
| **Strategy Pattern** | **REAL** | `cv_agent.py`, `pdf_service.py` vs `docx_service.py` | Selects parsing/chunking algorithm based on document properties |
| **Factory Pattern** | **REAL** | `DateNormalizer.normalize_to_iso()`, Pydantic models | Converts raw string inputs into validated domain objects |
| **Middleware Pattern** | **REAL** | `backend/app/main.py: CORSMiddleware`, `nginx.conf` | Cross-cutting request headers, CORS, and proxy timeouts |
| **Error Handling & Retry** | **REAL** | `entrypoint.sh`, `ollama_client.py`, `hr_chat_agent.py` | Graceful fallbacks, regex repair, quarantined DB backups |
| **Dependency Injection** | **PARTIAL** | `CVExtractionAgent(ollama_client=...)` | Constructor injection supported; FastAPI `Depends()` underutilized |
| **State Machine** | **PARTIAL** | `batch_jobs` table & SSE generator in `main.py` | Tracks batch states (`QUEUED` -> `PROCESSING` -> `COMPLETE`) |

---

## 1. Layered Architecture (Real Implementation)

### How It Works
The system is divided into distinct, decoupled tiers where each tier only depends on layers below it:
1. **Presentation Layer**: React 19 SPA (`frontend/src/App.tsx`). Completely decoupled from the database or Ollama; communicates purely via REST over JSON.
2. **Reverse Proxy / Gateway Layer**: Nginx (`frontend/nginx.conf`). Handles SSL termination at the edge, routes `/healthz`, and reverse-proxies `/api/` to the backend.
3. **Controller / Routing Layer**: FastAPI (`backend/app/main.py`). Validates HTTP headers, parses `multipart/form-data`, enforces maximum file sizes, and serializes responses via Pydantic schemas.
4. **Agent / Domain Orchestration Layer**: Autonomous Agents (`backend/app/agents/`):
   - `CVExtractionAgent`: Coordinates document text, Ollama SLM extraction, layout reconciliation, and grounding.
   - `CandidateEvaluatorAgent`: Contextual evaluator comparing structured profiles to job requirements.
   - `HRChatAgent`: Recruiter conversational copilot.
5. **Algorithmic Service Layer**: Pure domain logic (`backend/app/services/`):
   - `ExperienceCalculator`, `EvidenceVerifier`, `ExplainableScorer`, `InterviewEngine`. Completely independent of FastAPI and HTTP.
6. **Persistence Layer**: Data access (`backend/app/db/database.py`). Manages table definitions, WAL mode, connections, queries, and file BLOBs.

---

## 2. Service Layer Pattern (Real Implementation)

### Code Reference
- Files: `backend/app/services/experience_calculator.py`, `evidence_verifier.py`, `explainable_scorer.py`
- Classes: `ExperienceCalculator`, `EvidenceVerifier`, `ExplainableScorer`

### How It Works
Rather than embedding scoring algorithms and date math inside FastAPI route functions, business logic is isolated in stateless service classes.

**Example from `ExperienceCalculator` (`backend/app/services/experience_calculator.py:212`):**
```python
class ExperienceCalculator:
    @classmethod
    def calculate_total_experience_union(cls, employment_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Pure algorithmic calculation - zero HTTP or database dependencies
        # Returns normalized tenure, overlaps, and gaps
        ...
```
This enables running unit tests (`pytest backend/tests/`) against the business logic directly without spinning up a mock web server or database.

---

## 3. Repository Pattern (Real Implementation — Functional Form)

### Code Reference
- File: `backend/app/db/database.py`
- Functions: `save_candidate_record()`, `get_candidate_by_id()`, `get_all_candidates()`, `save_original_file()`, `check_duplicate_file()`, `save_job()`, `get_job_by_id()`

### How It Works
All raw SQL queries, transactions, connection lifecycles, and `sqlite3.Row` dictionary conversions are centralized in `database.py`. No route handler or agent ever writes inline SQL (`SELECT ...` or `INSERT ...`).

```python
# main.py simply calls:
db.save_candidate_record(cand_dict, source="UPLOADED", status="COMPLETED")
cand = db.get_candidate_by_id(candidate_id)
```

### Reality vs. Future Improvement
- **Current State**: Real functional repository module.
- **Future Improvement**: It does not implement an abstract interface (`class ICandidateRepository(ABC)`) to allow swapping SQLite for PostgreSQL. For a single-node SQLite architecture, the current functional module is clean and appropriate.

---

## 4. Adapter Pattern (Real Implementation)

### Code Reference
- File: `backend/app/services/ollama_client.py`
- Class: `OllamaClient`

### How It Works
The C++ Ollama daemon exposes a raw HTTP API (`POST /api/generate`) that accepts raw string prompts and returns raw text streams.

`OllamaClient` acts as an **Adapter**:
1. It adapts the unstructured Ollama HTTP endpoint into strongly typed asynchronous Python methods: `generate_json()` and `generate_text()`.
2. It wraps raw JSON serialization, sets hardware parameters (`num_thread: 2`), handles request timeouts (180s), and catches low-level `httpx.HTTPError` exceptions, converting them into clean domain errors.
3. It sanitizes model output via `_clean_and_parse_json()`, insulating the rest of the application from LLM formatting quirks (such as markdown code fences or trailing commas).

---

## 5. Strategy Pattern (Real Implementation)

### Code Reference
1. **Document Text Extraction Strategy**:
   - `backend/app/services/pdf_service.py: PDFService`
   - `backend/app/services/docx_service.py: DOCXService`
   - Selection in `backend/app/main.py:370`:
     ```python
     if ext == "pdf":
         cv_text = PDFService.extract_text_from_bytes(content_bytes)
     elif ext == "docx":
         cv_text = DOCXService.extract_text_from_bytes(content_bytes)
     else:
         cv_text = content_bytes.decode("utf-8", errors="ignore")
     ```
2. **Context Window Extraction Strategy**:
   - `backend/app/agents/cv_agent.py:79`:
     ```python
     est_tokens = self.estimate_token_count(cv_text)
     if est_tokens <= SAFE_CONTEXT_TOKEN_LIMIT:
         raw_data = await self._extract_full_document(cv_text, candidate_id)
     else:
         raw_data = await self._extract_sequential_chunks(cv_text, candidate_id)
     ```
   The strategy dynamically shifts between single-pass inference and multi-window chunking based on document length.

---

## 6. Factory Pattern (Real Implementation)

### Code Reference
- File: `backend/app/services/experience_calculator.py`
- Class: `DateNormalizer`
- Methods: `normalize_to_iso()`, `extract_start_end_strings()`

### How It Works
Resumes use dozens of inconsistent date formats: `"Jan 2020"`, `"01/2020"`, `"2020 - Present"`, `"March 2018 to Current"`.

`DateNormalizer` acts as an object factory:
- Receives heterogeneous, uncleaned string tokens or dictionary fragments.
- Uses cascading regex patterns and month lookup tables.
- Produces normalized, standardized date objects in `YYYY-MM` format with explicit `is_current` booleans.

Additionally, Pydantic schemas (`backend/app/schemas/candidate.py: CandidateExtraction(**data)`) act as data factories enforcing strict type validation and defaults.

---

## 7. Middleware Pattern (Real Implementation)

### Code Reference
- Files: `backend/app/main.py`, `frontend/nginx.conf`
- Implementations:
  1. **FastAPI CORSMiddleware**:
     ```python
     app.add_middleware(
         CORSMiddleware,
         allow_origins=["*"],
         allow_credentials=True,
         allow_methods=["*"],
         allow_headers=["*"],
     )
     ```
  2. **FastAPI Lifespan Context Manager**:
     `@asynccontextmanager async def lifespan(app: FastAPI)` manages database initialization and seed data loading before the application starts accepting HTTP traffic.
  3. **Nginx Reverse Proxy Middleware**:
     Enforces HTTP request timeouts (`proxy_read_timeout 300s`) and injects forwarding headers (`X-Real-IP`, `X-Forwarded-For`).

---

## 8. Error Handling & Retry Patterns (Real Implementation)

### Code Reference
1. **Corrupted Database Quarantine & Safety Trap**:
   - File: `scripts/entrypoint.sh:54-62`
   - If the persistent SQLite snapshot fails `PRAGMA integrity_check`, the entrypoint script refuses to overwrite it. It moves the file to a timestamped `.corrupted_backup` quarantine and halts container startup to prevent silent data loss.
2. **LLM Fallback Pattern in HR Chat Agent**:
   - File: `backend/app/agents/hr_chat_agent.py:40-43`
   ```python
   try:
       response_text = await self.ollama.generate_text(...)
   except Exception as e:
       logger.warning(f"Ollama chat generation failed ({e}). Using deterministic heuristic fallback.")
       response_text = self._heuristic_fallback_response(user_message, candidate_data, job_data, evaluation_data)
   ```
   If Ollama is busy, OOMs, or times out, the chat agent falls back to deterministic rule-based candidate summaries rather than crashing the user's chat session.

---

## 9. Dependency Injection (Partial Implementation)

### Code Reference
- File: `backend/app/agents/cv_agent.py:60`
  ```python
  def __init__(self, ollama_client: Optional[OllamaClient] = None):
      self.client = ollama_client or OllamaClient()
  ```
- File: `backend/app/agents/hr_chat_agent.py:15`
  ```python
  def __init__(self, ollama_client: Optional[OllamaClient] = None):
      self.ollama = ollama_client or OllamaClient()
  ```

### Reality vs. Future Improvement
- **Current State**: Manual constructor injection is supported on agents, allowing unit tests to pass mock Ollama clients.
- **Limitation**: In `backend/app/main.py`, agents are instantiated as global module singletons (`cv_agent = CVExtractionAgent()`) rather than being resolved per-request using FastAPI's `Depends()` framework.
- **Future Improvement**: Refactor `main.py` route signatures to use `agent: CVExtractionAgent = Depends(get_cv_agent)`.

---

## 10. State Machine Pattern (Partial Implementation)

### Code Reference
- File: `backend/app/main.py:403` (`/api/batch-upload` & `/api/batch-progress/{batch_id}`)
- File: `backend/app/db/database.py:133` (`batch_jobs` table)

### How It Works
Batch processing tracks document lifecycles through distinct states:
`QUEUED` $\rightarrow$ `PROCESSING` $\rightarrow$ `COMPLETED` (or `FAILED`).

Clients open a Server-Sent Events (SSE) stream (`/api/batch-progress/{batch_id}`) which emits real-time progress events until the terminal `COMPLETED` state is reached.
