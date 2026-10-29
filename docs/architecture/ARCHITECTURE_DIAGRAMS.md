# CVScreen: Complete Architecture Diagrams

**Document**: `ARCHITECTURE_DIAGRAMS.md`  
**Purpose**: Visual architecture reference covering system context, components, runtime sequences, data pipelines, infrastructure topology, and error recovery.

---

## 1. System Context Diagram (C4 Level 1)

This diagram illustrates the high-level boundary of the CVScreen system, the human actors who interact with it, and its external/managed infrastructure dependencies.

```mermaid
flowchart TB
    subgraph Users["Human Actors"]
        Recruiter["Recruiter / Hiring Manager\n(Web Browser)"]
    end

    subgraph SystemBoundary["CVScreen Intelligence Platform"]
        CVScreenApp["CVScreen System\n(Azure Container Apps Environment)\n- React 19 Frontend (SPA)\n- FastAPI Backend (Python 3.11)\n- Local Ollama Runtime (Qwen 2.5 1.5B)\n- SQLite 3 (WAL Mode)"]
    end

    subgraph AzureCloud["Azure Cloud Managed Infrastructure"]
        ACR["Azure Container Registry\n(crcvscreenexample)\n- Private Docker Images"]
        AzureFiles["Azure Storage Account\n(stcvscreenprodxg4dry2ol)\n- Azure Files Share (cvdatamount)\n- CIFS / SMB Persistent Volume"]
        LogAnalytics["Azure Monitor & Log Analytics\n- Application Insights Telemetry"]
    end

    Recruiter -->|"HTTPS / Port 443 (Browse Candidates, Upload CVs, Chat)"| CVScreenApp
    CVScreenApp -->|"Pull Container Images (Deploy / Restart)"| ACR
    CVScreenApp -->|"Mount Persistent Volume (/app/data)"| AzureFiles
    CVScreenApp -->|"Stream Logs & Metric Events"| LogAnalytics
```

---

## 2. Component Architecture Diagram (C4 Level 2)

Detailed view of the internal components inside the Frontend and Backend pods, and how they communicate.

```mermaid
flowchart LR
    subgraph FrontendContainer["Frontend Container (Port 80)"]
        ReactApp["React 19 SPA\n(Vite + TypeScript)\n- Candidate Inspector\n- Multi-Stage Upload\n- HR Chat Interface\n- Benchmarks View"]
        NginxProxy["Nginx Reverse Proxy\n- Static File Server\n- /healthz Endpoint\n- /api/* Proxy (300s timeout)"]
        ReactApp -->|"HTTP Internal"| NginxProxy
    end

    subgraph BackendContainer["Backend Container (Port 8000)"]
        Uvicorn["Uvicorn ASGI Server"]
        FastAPIApp["FastAPI Router (main.py)\n- Upload & Batch Endpoints\n- Scoring & Matching\n- Recruiter Chat API"]
        
        subgraph Services["Application Services"]
            PDFSvc["PDFService (pypdf)"]
            DocxSvc["DOCXService (python-docx)"]
            LayoutEng["DocumentLayoutEngine (Regex/Heuristics)"]
            ExpCalc["ExperienceCalculator (Interval Union)"]
            EvidenceVer["EvidenceVerifier (Grounding)"]
            ExplainScorer["ExplainableScorer (4 Pillars)"]
            InterviewEng["InterviewEngine (Questions)"]
            JDExtract["JDExtractor (Role Parser)"]
        end

        subgraph Agents["Autonomous AI Agents"]
            CVAgent["CVExtractionAgent\n(Structured Extraction)"]
            EvalAgent["CandidateEvaluatorAgent\n(Auditable Evaluation)"]
            HRChat["HRChatAgent\n(Recruiter Copilot)"]
        end

        subgraph OllamaRuntime["Local AI Engine (Port 11434)"]
            OllamaDaemon["Ollama C++ Daemon (127.0.0.1)"]
            QwenModel["Qwen 2.5 1.5B Weights\n(Container RAM / In-Memory)"]
            OllamaDaemon --> QwenModel
        end

        subgraph StorageLayer["Data & Persistence Layer"]
            SQLiteLocal["SQLite Engine (WAL Mode)\n/app/local_data/cv_screening.db"]
            BackupDaemon["Sync Daemon (entrypoint.sh)\nOnline Backup API (every 60s)"]
            SQLitePersist["Azure Files Volume\n/app/data/cv_screening.db"]
            
            SQLiteLocal -->|"PRAGMA backup()"| BackupDaemon
            BackupDaemon -->|"Write atomic snapshot"| SQLitePersist
        end

        Uvicorn --> FastAPIApp
        FastAPIApp --> PDFSvc
        FastAPIApp --> DocxSvc
        FastAPIApp --> CVAgent
        FastAPIApp --> EvalAgent
        FastAPIApp --> HRChat
        FastAPIApp --> ExplainScorer
        FastAPIApp --> SQLiteLocal

        CVAgent --> LayoutEng
        CVAgent --> EvidenceVer
        CVAgent --> ExpCalc
        CVAgent -->|"OllamaClient (HTTP)"| OllamaDaemon

        HRChat -->|"OllamaClient (HTTP)"| OllamaDaemon
        EvalAgent --> ExpCalc
        ExplainScorer --> InterviewEng
    end

    NginxProxy -->|"HTTP /api/* (Internal VNet)"| Uvicorn
```

---

## 3. Sequence Diagram: Resume Upload & AI Evaluation

Traces the execution sequence through every layer when a user submits a resume file.

```mermaid
sequenceDiagram
    autonumber
    actor User as Recruiter
    participant Browser as React SPA (App.tsx)
    participant Nginx as Nginx Proxy
    participant API as FastAPI (main.py)
    participant Parser as PDF / DOCX Service
    participant Agent as CVExtractionAgent
    participant Ollama as Ollama (Qwen 2.5)
    participant Verifier as EvidenceVerifier
    participant Calc as ExperienceCalculator
    participant DB as SQLite Database

    User->>Browser: Selects "Upload CV" & Drops file.pdf
    Browser->>Browser: Sets uploadStage = 'reading'
    Browser->>Nginx: POST /api/upload-cv (multipart/form-data)
    Nginx->>API: Proxy pass POST /api/upload-cv
    API->>API: Validate file extension & PDF magic bytes (%PDF)
    API->>API: Compute SHA-256 hash
    API->>DB: Query existing hash in original_files
    alt Duplicate Detected & Action != replace
        API-->>Nginx: 409 Conflict (Duplicate details)
        Nginx-->>Browser: 409 Conflict
        Browser-->>User: Show duplicate warning modal
    end
    API->>Parser: extract_text_from_bytes(content_bytes)
    Parser-->>API: Raw cleaned CV text string
    API->>DB: save_original_file(candidate_id, file_bytes)
    API->>Agent: extract_candidate(cv_text, candidate_id)
    Browser->>Browser: Sets uploadStage = 'analyzing'
    Agent->>Ollama: POST /api/generate (System prompt, JSON schema, cv_text)
    Ollama->>Ollama: Model forward pass (num_thread: 2, num_predict: 1024)
    Ollama-->>Agent: Raw JSON String
    Agent->>Agent: _clean_and_parse_json() & reconcile layout positions
    Browser->>Browser: Sets uploadStage = 'verifying'
    Agent->>Verifier: verify_and_ground_candidate(raw_json, cv_text)
    Verifier->>Verifier: Locate exact character offsets for every skill/degree
    Verifier-->>Agent: Grounded Evidence Items (VERIFIED / UNVERIFIED)
    Agent->>Calc: calculate_total_experience_union(employment_history)
    Calc->>Calc: Normalize YYYY-MM & merge overlapping intervals
    Calc-->>Agent: Non-overlapping total tenure & career gaps
    Agent-->>API: Validated CandidateExtraction Pydantic Object
    API->>DB: save_candidate_record(cand_dict)
    API-->>Nginx: HTTP 200 OK (CandidateExtraction JSON)
    Nginx-->>Browser: HTTP 200 OK
    Browser->>Browser: Append candidate to list & select active
    Browser->>API: GET /api/candidates/{id}/evidence-graph
    API->>API: ExplainableScorer.calculate_explainable_score()
    API->>API: InterviewEngine.generate_verification_questions()
    API-->>Browser: Return 4-Pillar Score, Audit Trail, Interview Questions
    Browser-->>User: Render Candidate Inspector, Verified Pills & Score Dial
```

---

## 4. Data-Flow Diagram (DFD)

Traces how candidate information transitions from raw binary to structured, verified intelligence.

```mermaid
flowchart TD
    RawFile["1. Raw File (PDF / DOCX / TXT Binary)"] --> Parser["2. Parser Layer\n- PDFService (pypdf)\n- DOCXService (python-docx)"]
    RawFile -->|"SHA-256 Hash + Raw BLOB"| OriginalFilesTable[("original_files Table\n(SQLite)")]
    
    Parser -->|"Raw UTF-8 Text Stream"| LayoutEngine["3. DocumentLayoutEngine\n- Regex Header Extractor\n- Section Splitter\n- Layout Employment Ground Truth"]
    Parser -->|"Raw UTF-8 Text Stream"| OllamaInference["4. Ollama Qwen 2.5 1.5B\n- Structured JSON Entity Extraction\n- Skills, Roles, Education, Timeline"]

    LayoutEngine -->|"Layout-verified positions"| Reconciler["5. Entity Reconciler & Normalizer\n- Deduplicate\n- Filter hallucinations / bullet points"]
    OllamaInference -->|"LLM extracted candidates"| Reconciler

    Reconciler -->|"Candidate Extraction Draft"| Verifier["6. EvidenceVerifier\n- Substring matching\n- char_offset_start & end\n- Grounding Coverage %"]
    Parser -->|"Raw CV Text"| Verifier

    Verifier -->|"Verified Entities"| ExpCalc["7. ExperienceCalculator\n- DateNormalizer (YYYY-MM)\n- Interval Union Set Merging\n- Overlap & Gap Detection"]

    ExpCalc -->|"Structured Candidate Record"| CandidatesTable[("candidates Table\n(SQLite /app/local_data)")]
    
    CandidatesTable --> Matcher["8. Matching & Explainable Scoring Engine\n- 4-Pillar Weighted Score\n- Core Skills (40%)\n- Experience Truth (25%)\n- Domain Match (20%)\n- Evidence Coverage (15%)"]
    JobTable[("jobs Table\n(SQLite)")] --> Matcher

    Matcher -->|"Audit Report & Score Breakdown"| MatchResultsTable[("match_results Table\n(SQLite)")]
    Matcher --> RecruiterUI["9. Recruiter Dashboard (React UI)\n- Evidence Audit Trail\n- Verification Interview Questions\n- HR Chat Copilot"]
```

---

## 5. Deployment Topology Diagram (Azure Cloud)

Illustrates the network isolation, Azure Container Apps hosting, and persistent file share attachment in production.

```mermaid
flowchart TB
    InternetUser(("Recruiter Browser\n(Internet)"))

    subgraph AzureSub["Azure Subscription (rg-cvscreening-prod / eastus2)"]
        AzureEdge["Azure Front Door / Managed Ingress\n- TLS 1.3 Termination (*.azurecontainerapps.io)\n- Public IP Ingress"]

        subgraph ContainerAppsEnv["Container Apps Managed Environment (cae-cvscreen-prod)"]
            
            subgraph FrontendApp["Frontend Container App (app-cvscreen-frontend-prod)"]
                FrontendPod["Frontend Pod\n- Replicas: min 1, max 5\n- CPU: 0.5 vCPU, RAM: 1.0 GiB\n- Port 80 (Nginx)\n- Static React 19 SPA Build"]
            end

            subgraph BackendApp["Backend Container App (app-cvscreen-backend-prod)"]
                BackendPod["Backend Pod\n- Replicas: min 0, max 1 (Scale to Zero)\n- CPU: 2.0 vCPU, RAM: 4.0 GiB\n- Internal Ingress only (Port 8000)\n- Uvicorn FastAPI Server\n- Local Ollama Process (127.0.0.1:11434)\n- Ephemeral SSD: /app/local_data/cv_screening.db"]
            end

            FrontendPod -->|"Internal HTTP Proxy (port 8000)\nPrivate FQDN: app-cvscreen-backend-prod.internal"| BackendPod
        end

        subgraph Registry["Private Container Registry"]
            ACR["Azure Container Registry (Standard)\ncrcvscreenexample.azurecr.io\n- cvscreening-frontend:latest\n- cvscreening-backend:latest"]
        end

        subgraph StorageAccount["Azure Storage Account (Standard LRS)"]
            AzureFileShare["Azure Files Share (cvdatamount)\n- Mounted via CIFS/SMB to /app/data\n- Houses durable SQLite snapshot"]
        end

        BackendPod -->|"CIFS Volume Mount (/app/data)"| AzureFileShare
        ACR -.->|"Pull on revision rollout"| FrontendPod
        ACR -.->|"Pull on revision rollout"| BackendPod
    end

    InternetUser -->|"HTTPS (Port 443)"| AzureEdge
    AzureEdge -->|"Route to Target Port 80"| FrontendPod
```

---

## 6. Error-Flow & Fault Recovery Diagram

Covers all failure modes: corrupt files, AI timeouts, database locks, and container restarts.

```mermaid
flowchart TD
    UploadTrigger["User Uploads Resume"] --> CheckMagic{"Validate Header & Format?"}
    
    CheckMagic -- "No (%PDF missing / bad extension)" --> ErrFormat["HTTP 400 Bad Request\n'Invalid file header / Unsupported extension'"]
    CheckMagic -- "Yes" --> CheckSize{"File Size <= 10MB?"}

    CheckSize -- "No (>10MB)" --> ErrSize["HTTP 413 Payload Too Large\n'File exceeds 10MB limit'"]
    CheckSize -- "Yes" --> CheckDup{"SHA-256 in DB?"}

    CheckDup -- "Yes & duplicate_action null" --> ErrDup["HTTP 409 Conflict\n'Duplicate resume detected' (Prompt keep/replace)"]
    CheckDup -- "No or replace" --> TextExtract{"Extract Text (pypdf/docx)?"}

    TextExtract -- "Empty Text / Corrupt PDF" --> ErrExtract["HTTP 422 Unprocessable Entity\n'Could not extract readable text (scanned/encrypted)'"]
    TextExtract -- "Success" --> OllamaCall{"Ollama HTTP Call\n(180s Timeout)"}

    OllamaCall -- "Connection Refused / Crash" --> FallbackOllama["Catch RequestError\nLog fatal event -> Restart Ollama daemon"]
    OllamaCall -- "Malformed JSON from LLM" --> JsonRepair{"_clean_and_parse_json()\nRegex repair trailing commas/quotes"}
    
    JsonRepair -- "Repaired" --> VerifierStep["Proceed to EvidenceVerifier"]
    JsonRepair -- "Unrecoverable" --> ErrAI["HTTP 500 AI Extraction Failed\nReturn explicit diagnostic message"]

    OllamaCall -- "Success" --> VerifierStep
    VerifierStep --> ExpCalcStep["ExperienceCalculator (Deterministic Union)"]
    ExpCalcStep --> DBSave{"Save to SQLite (/app/local_data)?"}

    DBSave -- "Locked / Disk Full" --> DBLockRetry["Retry with exponential backoff\n(WAL mode allows concurrent readers)"]
    DBSave -- "Success" --> SyncCheck{"Sync Daemon Snapshot (/app/data)?"}

    SyncCheck -- "Corruption detected in snapshot" --> QuarantineCorrupt["Quarantine corrupted snapshot to .corrupt_backup\nPreserve working local DB"]
    SyncCheck -- "Integrity OK" --> Complete["HTTP 200 OK -> Deliver to UI"]
```
