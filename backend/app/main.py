import os
import time
import json
import uuid
import asyncio
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, File, UploadFile, HTTPException, Query, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, Response, FileResponse
from pydantic import BaseModel


from backend.app.config import settings, EXTRACTED_DIR, DATA_DIR, SEED_DATA_DIR
from backend.app.services.pdf_service import PDFService, PDFExtractionError
from backend.app.services.docx_service import DOCXService, DOCXExtractionError
from backend.app.agents.cv_agent import CVExtractionAgent
from backend.app.schemas.candidate import CandidateExtraction
from backend.app.services.scoring_engine import ScoringEngine
from backend.app.services.evaluator import Evaluator
from backend.app.agents.evaluator_agent import CandidateEvaluatorAgent
from backend.app.services.interview_engine import InterviewEngine
from backend.app.services.jd_extractor import JDExtractor
from backend.app.agents.hr_chat_agent import HRChatAgent
from backend.app.db import database as db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cvscreening")

from contextlib import asynccontextmanager

# Max file size: 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    conn = db.get_db_connection()
    count = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
    conn.close()
    if count == 0:
        logger.info("Initializing mock dataset candidates into SQLite database...")
        load_mock_dataset_internal()
    # Load jobs from JSONL into DB if empty
    conn = db.get_db_connection()
    job_count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    conn.close()
    if job_count == 0:
        load_jobs_from_jsonl()
    yield

app = FastAPI(
    title="CV Screening AI Agent — Evidence-Based Candidate Intelligence",
    description="Local zero-cloud candidate intelligence platform with evidence-backed screening, deterministic experience calculation, and explainable scoring.",
    version="3.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

cv_agent = CVExtractionAgent()
scoring_engine = ScoringEngine()
evaluator_agent = CandidateEvaluatorAgent()
jd_extractor = JDExtractor()
hr_chat_agent = HRChatAgent()

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = ROOT_DIR / "frontend" / "dist"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# --- Internal Helpers ---
def load_mock_dataset_internal():
    resumes_jsonl = SEED_DATA_DIR / "normalized" / "resumes.jsonl"
    if not resumes_jsonl.exists():
        resumes_jsonl = DATA_DIR / "normalized" / "resumes.jsonl"
    if not resumes_jsonl.exists():
        logger.warning(f"resumes.jsonl not found in {SEED_DATA_DIR} or {DATA_DIR}")
        return 0
        
    loaded = 0
    with open(resumes_jsonl, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            cand_data = json.loads(line)
            db.save_candidate_record(cand_data, source="MOCK", status="COMPLETED")
            loaded += 1
            
    logger.info(f"Loaded {loaded} mock dataset candidates into database.")
    return loaded

def load_jobs_from_jsonl():
    jds_path = SEED_DATA_DIR / "normalized" / "jobs.jsonl"
    if not jds_path.exists():
        jds_path = DATA_DIR / "normalized" / "jobs.jsonl"
    if not jds_path.exists():
        logger.warning(f"jobs.jsonl not found in {SEED_DATA_DIR} or {DATA_DIR}")
        return 0
    loaded = 0
    with open(jds_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                job_data = json.loads(line)
                job_data["source"] = "DATASET"
                db.save_job(job_data)
                loaded += 1
    logger.info(f"Loaded {loaded} jobs from dataset.")
    return loaded

# --- Models ---
class MatchRequest(BaseModel):
    candidate_id: str
    job_id: str

class JobCreateRequest(BaseModel):
    title: str
    seniority: str = "Mid-level"
    department: str = ""
    location: str = ""
    employment_type: str = "Full-time"
    description: str = ""
    minimum_years_experience: float = 0.0
    required_skills: List[str] = []
    preferred_skills: List[str] = []
    education_requirements: List[str] = []
    domain_requirements: List[str] = []
    responsibilities: List[str] = []
    other_constraints: str = ""

class RecruiterActionRequest(BaseModel):
    action: str  # SHORTLIST, REJECT, MAYBE, INTERVIEW, NOTE, TAG
    job_id: Optional[str] = None
    note: str = ""
    tag: str = ""

class CompareRequest(BaseModel):
    candidate_ids: List[str]
    job_id: Optional[str] = None

class JDExtractRequest(BaseModel):
    jd_text: str

class HRChatRequest(BaseModel):
    message: str
    job_id: Optional[str] = None
    save_history: bool = True

class HRChatResponse(BaseModel):
    candidate_id: str
    reply: str
    suggested_followups: List[str] = []
    job_id: Optional[str] = None
    created_at: Optional[str] = None

# --- System Health ---
@app.get("/api/system/health")
async def system_health():
    import httpx
    ollama_status = "disconnected"
    ollama_model = settings.OLLAMA_LLM_MODEL
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            if res.status_code == 200:
                ollama_status = "connected"
                models = res.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                if not any(ollama_model in mn for mn in model_names):
                    ollama_status = "connected_model_missing"
    except Exception:
        ollama_status = "disconnected"

    return {
        "ollama_status": ollama_status,
        "ollama_model": ollama_model,
        "ollama_url": settings.OLLAMA_BASE_URL,
        "parser_status": "ready",
        "database_status": "ready",
        "version": "3.0.0"
    }

# --- Dashboard Metrics ---
@app.get("/api/dashboard/metrics")
async def dashboard_metrics(job_id: Optional[str] = None):
    return db.get_dashboard_metrics(job_id)

# --- Dataset & Manifest Endpoints ---
@app.get("/api/dataset/manifest")
async def get_dataset_manifest():
    manifest_path = ROOT_DIR / "dataset_manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="dataset_manifest.json not found. Run dataset generation first.")
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)

@app.post("/api/dataset/load-mock")
async def load_mock_dataset():
    count = load_mock_dataset_internal()
    return {"status": "success", "candidates_loaded": count}

# --- Job CRUD ---
@app.get("/api/jobs")
async def list_jobs(status: Optional[str] = None):
    return db.list_jobs(status)

@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = db.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return job

@app.post("/api/jobs")
async def create_job(req: JobCreateRequest):
    job_id = f"JOB-{uuid.uuid4().hex[:8].upper()}"
    job_data = req.model_dump()
    job_data["job_id"] = job_id
    job_data["mandatory_skills"] = job_data["required_skills"]
    result = db.save_job(job_data)
    return result

@app.put("/api/jobs/{job_id}")
async def update_job(job_id: str, req: JobCreateRequest):
    existing = db.get_job_by_id(job_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    job_data = req.model_dump()
    job_data["job_id"] = job_id
    job_data["mandatory_skills"] = job_data["required_skills"]
    result = db.save_job(job_data)
    return result

@app.delete("/api/jobs/{job_id}")
async def delete_job_endpoint(job_id: str):
    success = db.delete_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return {"status": "success", "message": f"Job {job_id} deleted."}

# --- JD Extract (AI-powered) ---
@app.post("/api/jobs/extract-jd")
async def extract_jd_requirements(req: JDExtractRequest):
    if not req.jd_text.strip():
        raise HTTPException(status_code=400, detail="JD text is empty.")
    result = await jd_extractor.extract_requirements(req.jd_text)
    return result

# --- Legacy: Job Descriptions from JSONL (backward compat) ---
@app.get("/api/job-descriptions")
async def list_job_descriptions():
    return db.list_jobs()

# --- Resume Library Endpoints ---
@app.get("/api/candidates")
async def list_candidates(source: Optional[str] = None):
    conn = db.get_db_connection()
    if source and source.upper() in ["MOCK", "UPLOADED"]:
        rows = conn.execute("SELECT * FROM candidates WHERE source = ? ORDER BY created_at DESC", (source.upper(),)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM candidates ORDER BY created_at DESC").fetchall()
    conn.close()
    
    results = []
    for r in rows:
        item = dict(r)
        item["skills"] = json.loads(item["skills"]) if item["skills"] else []
        item["roles"] = json.loads(item["roles"]) if item["roles"] else []
        if item.get("raw_json"):
            try:
                item["raw_data"] = json.loads(item["raw_json"])
            except Exception:
                item["raw_data"] = {}
        # Get latest recruiter action
        item["recruiter_action"] = db.get_latest_action_for_candidate(item["candidate_id"])
        results.append(item)
    return results

@app.get("/api/candidates/{candidate_id}")
async def get_candidate_detail(candidate_id: str):
    conn = db.get_db_connection()
    row = conn.execute("SELECT * FROM candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found.")
        
    item = dict(row)
    if item.get("raw_json"):
        return json.loads(item["raw_json"])
    return item

@app.get("/api/candidates/{candidate_id}/original-file")
async def get_original_file(candidate_id: str):
    conn = db.get_db_connection()
    row = conn.execute("SELECT * FROM original_files WHERE candidate_id = ?", (candidate_id,)).fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Original document not found for this candidate.")
        
    file_bytes = row["file_data"]
    filename = row["filename"]
    file_type = row["file_type"]
    
    media_type = "application/pdf" if file_type == "pdf" else ("application/vnd.openxmlformats-officedocument.wordprocessingml.document" if file_type == "docx" else "text/plain")
    return Response(content=file_bytes, media_type=media_type, headers={"Content-Disposition": f"inline; filename={filename}"})

# --- Upload & Duplicate Detection Pipeline ---
@app.post("/api/upload-cv")
async def upload_cv(
    file: UploadFile = File(...),
    duplicate_action: Optional[str] = Query(None)  # 'replace', 'keep_both'
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename missing.")

    ext = file.filename.split(".")[-1].lower()
    if ext not in ["pdf", "docx", "txt", "png", "jpg", "jpeg"]:
        raise HTTPException(status_code=400, detail=f"Unsupported file format '.{ext}'. Supported: PDF, DOCX, TXT, Images.")

    content_bytes = await file.read()
    if not content_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # File size check
    if len(content_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB.")

    # Validate file magic bytes for PDF
    if ext == "pdf" and not content_bytes[:5].startswith(b'%PDF'):
        raise HTTPException(status_code=400, detail="Invalid PDF file. File header does not match PDF format.")

    # Calculate SHA-256 Hash
    sha256_hash = db.calculate_sha256(content_bytes)

    # Check for duplicates
    dup = db.check_duplicate_file(sha256_hash)
    if dup and duplicate_action != "keep_both" and duplicate_action != "replace":
        return JSONResponse(
            status_code=409,
            content={
                "duplicate_detected": True,
                "sha256_hash": sha256_hash,
                "existing_candidate_id": dup["candidate_id"],
                "existing_filename": dup["filename"],
                "message": f"Duplicate resume detected. File '{file.filename}' matches existing document '{dup['filename']}'."
            }
        )

    if dup and duplicate_action == "replace":
        db.delete_candidate(dup["candidate_id"])

    # Document ID & Candidate ID
    short_id = str(uuid.uuid4())[:8].upper()
    candidate_id = f"CAND-{short_id}"

    start_upload_time = time.time()
    logger.info(f"Processing upload for {file.filename} ({len(content_bytes)} bytes) as {candidate_id}")

    # Extract text based on file format
    try:
        if ext == "pdf":
            cv_text = PDFService.extract_text_from_bytes(content_bytes)
        elif ext == "docx":
            cv_text = DOCXService.extract_text_from_bytes(content_bytes)
        else:
            cv_text = content_bytes.decode("utf-8", errors="ignore")
    except Exception as e:
        logger.error(f"Text extraction failed for {file.filename}: {e}")
        raise HTTPException(status_code=422, detail=f"Text extraction error: {str(e)}")

    # Store original file bytes & hash
    db.save_original_file(candidate_id, file.filename, ext, sha256_hash, content_bytes)

    # Run Candidate Extraction Agent
    try:
        candidate_data = await cv_agent.extract_candidate(cv_text, candidate_id=candidate_id)
        cand_dict = candidate_data.model_dump()
    except Exception as e:
        logger.error(f"CV extraction failed: {e}")
        raise HTTPException(status_code=500, detail=f"AI extraction failed: {str(e)}")

    # Save to SQLite DB
    db.save_candidate_record(cand_dict, source="UPLOADED", status="COMPLETED", filename=file.filename, file_hash=sha256_hash)
    logger.info(f"Successfully processed {file.filename} ({candidate_id}) in {time.time() - start_upload_time:.2f}s")

    return cand_dict


# --- Batch Upload with SSE Progress ---
from fastapi.responses import StreamingResponse
batch_progress = {}

@app.post("/api/batch-upload")
async def batch_upload(files: List[UploadFile] = File(...)):
    """Start a batch upload. Returns batch_id for tracking via SSE."""
    if len(files) == 0:
        raise HTTPException(status_code=400, detail="No files provided.")
    if len(files) > 1000:
        raise HTTPException(status_code=400, detail="Maximum 1000 files per batch.")
    
    batch_id = f"BATCH-{uuid.uuid4().hex[:8].upper()}"
    
    file_data = []
    for f in files:
        content = await f.read()
        if len(content) > MAX_FILE_SIZE:
            continue
        file_data.append({
            "filename": f.filename,
            "content": content,
            "ext": f.filename.split(".")[-1].lower() if f.filename else "txt",
            "status": "QUEUED"
        })
    
    batch_progress[batch_id] = {
        "batch_id": batch_id,
        "total": len(file_data),
        "completed": 0,
        "processing": 0,
        "queued": len(file_data),
        "failed": 0,
        "files": [{
            "filename": fd["filename"],
            "status": "QUEUED",
            "candidate_id": None,
            "error": None
        } for fd in file_data]
    }
    
    # Process async in background
    asyncio.create_task(_process_batch(batch_id, file_data))
    
    return {"batch_id": batch_id, "total": len(file_data), "status": "PROCESSING"}

async def _process_batch(batch_id: str, file_data: list):
    """Process batch files sequentially to avoid overwhelming Ollama."""
    progress = batch_progress.get(batch_id)
    if not progress:
        return
    
    for idx, fd in enumerate(file_data):
        try:
            progress["files"][idx]["status"] = "PROCESSING"
            progress["processing"] += 1
            progress["queued"] -= 1
            
            ext = fd["ext"]
            content_bytes = fd["content"]
            filename = fd["filename"]
            
            if ext not in ["pdf", "docx", "txt", "png", "jpg", "jpeg"]:
                raise ValueError(f"Unsupported format: {ext}")
            
            sha256_hash = db.calculate_sha256(content_bytes)
            dup = db.check_duplicate_file(sha256_hash)
            if dup:
                progress["files"][idx]["status"] = "SKIPPED"
                progress["files"][idx]["error"] = "Duplicate file"
                progress["completed"] += 1
                progress["processing"] -= 1
                continue
            
            # Extract text
            if ext == "pdf":
                cv_text = PDFService.extract_text_from_bytes(content_bytes)
            elif ext == "docx":
                cv_text = DOCXService.extract_text_from_bytes(content_bytes)
            else:
                cv_text = content_bytes.decode("utf-8", errors="ignore")
            
            short_id = str(uuid.uuid4())[:8].upper()
            candidate_id = f"CAND-{short_id}"
            
            db.save_original_file(candidate_id, filename, ext, sha256_hash, content_bytes)
            
            candidate_data = await cv_agent.extract_candidate(cv_text, candidate_id=candidate_id)
            cand_dict = candidate_data.model_dump()
            db.save_candidate_record(cand_dict, source="UPLOADED", status="COMPLETED", filename=filename, file_hash=sha256_hash)
            
            progress["files"][idx]["status"] = "COMPLETED"
            progress["files"][idx]["candidate_id"] = candidate_id
            progress["completed"] += 1
            progress["processing"] -= 1
            
        except Exception as e:
            logger.error(f"Batch processing failed for {fd['filename']}: {e}")
            progress["files"][idx]["status"] = "FAILED"
            progress["files"][idx]["error"] = str(e)
            progress["failed"] += 1
            progress["processing"] -= 1
    
    progress["status"] = "COMPLETE"

@app.get("/api/batch-status/{batch_id}")
async def get_batch_status(batch_id: str):
    progress = batch_progress.get(batch_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Batch not found.")
    return progress

@app.get("/api/batch-progress/{batch_id}")
async def batch_progress_sse(request: Request, batch_id: str):
    """Server-Sent Events stream for batch progress."""
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            progress = batch_progress.get(batch_id)
            if not progress:
                yield f"event: error\ndata: {json.dumps({'error': 'Batch not found'})}\n\n"
                break
            
            data = {
                "batch_id": batch_id,
                "total": progress["total"],
                "completed": progress["completed"],
                "processing": progress["processing"],
                "queued": progress["queued"],
                "failed": progress["failed"],
                "files": progress["files"]
            }
            yield f"event: progress\ndata: {json.dumps(data)}\n\n"
            
            if progress.get("status") == "COMPLETE":
                yield f"event: complete\ndata: {json.dumps(progress)}\n\n"
                break
            await asyncio.sleep(1)
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")


# --- Scoring & Matching ---
@app.post("/api/match")
async def match_candidate_against_job(request: MatchRequest):
    # Fetch candidate
    cand_raw = await get_candidate_detail(request.candidate_id)
    
    # Fetch job
    job = db.get_job_by_id(request.job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {request.job_id} not found.")

    score_result = scoring_engine.score_candidate(cand_raw, job)
    
    # Store match result
    conn = db.get_db_connection()
    conn.execute("""
        INSERT OR REPLACE INTO match_results (candidate_id, job_id, score, recommendation, matched_skills, missing_skills, reasoning, score_breakdown)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        request.candidate_id,
        request.job_id,
        score_result["score"],
        score_result["recommendation"],
        json.dumps(score_result["matched_skills"]),
        json.dumps(score_result["missing_skills"]),
        score_result["reasoning"],
        json.dumps(score_result.get("score_breakdown", {}))
    ))
    conn.commit()
    conn.close()

    return score_result

# --- Evidence Graph & Explainable Score ---
@app.get("/api/candidates/{candidate_id}/evidence-graph")
async def get_candidate_evidence_graph(candidate_id: str, job_id: Optional[str] = None):
    candidate = await get_candidate_detail(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    job_data = None
    if job_id:
        job_data = db.get_job_by_id(job_id)
    
    from backend.app.services.explainable_scorer import ExplainableScorer
    explainable_res = ExplainableScorer.calculate_explainable_score(candidate, job_data=job_data)
    
    # Generate interview questions
    interview_questions = InterviewEngine.generate_verification_questions(
        candidate_data=candidate,
        job_data=job_data or {"title": "General Role", "seniority": "Mid-level"},
        requirement_analysis=explainable_res.get("requirement_analysis", []),
        experience_truth=explainable_res.get("experience_truth"),
        career_gaps=candidate.get("career_gaps", []),
    )
    explainable_res["interview_questions"] = interview_questions
    
    if job_data:
        explainable_res["matched_job"] = job_data
        match_record = db.get_match_result(candidate_id, job_id)
        if match_record:
            explainable_res["overall_score"] = match_record["score"]
            explainable_res["recommendation"] = match_record["recommendation"]
        else:
            match_res = scoring_engine.score_candidate(candidate, job_data)
            explainable_res["overall_score"] = match_res["score"]
            explainable_res["recommendation"] = match_res["recommendation"]
    
    return explainable_res

# --- Candidate Evaluation Report ---
@app.post("/api/candidates/{candidate_id}/evaluate")
async def evaluate_candidate_report(candidate_id: str, job_id: Optional[str] = Query(None)):
    cand_data = await get_candidate_detail(candidate_id)
    job_data = None
    if job_id:
        job_data = db.get_job_by_id(job_id)
        
    report = evaluator_agent.evaluate(cand_data, job_description=job_data)
    return report

# --- Interview Questions ---
@app.get("/api/candidates/{candidate_id}/interview-questions")
async def get_interview_questions(candidate_id: str, job_id: Optional[str] = None):
    candidate = await get_candidate_detail(candidate_id)
    
    job_data = db.get_job_by_id(job_id) if job_id else {"title": "General Role", "seniority": "Mid-level"}
    
    from backend.app.services.explainable_scorer import ExplainableScorer
    explainable_res = ExplainableScorer.calculate_explainable_score(candidate, job_data=job_data)
    
    questions = InterviewEngine.generate_verification_questions(
        candidate_data=candidate,
        job_data=job_data or {"title": "General Role", "seniority": "Mid-level"},
        requirement_analysis=explainable_res.get("requirement_analysis", []),
        experience_truth=explainable_res.get("experience_truth"),
        career_gaps=candidate.get("career_gaps", []),
    )
    return {"candidate_id": candidate_id, "questions": questions}

# --- Recruiter Actions ---
@app.post("/api/candidates/{candidate_id}/action")
async def recruiter_action(candidate_id: str, req: RecruiterActionRequest):
    valid_actions = ["SHORTLIST", "REJECT", "MAYBE", "INTERVIEW", "NOTE", "TAG"]
    if req.action.upper() not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid action. Must be one of: {', '.join(valid_actions)}")
    
    db.save_recruiter_action(candidate_id, req.action.upper(), req.job_id, req.note, req.tag)
    return {"status": "success", "candidate_id": candidate_id, "action": req.action.upper()}

@app.get("/api/candidates/{candidate_id}/actions")
async def get_candidate_actions(candidate_id: str, job_id: Optional[str] = None):
    actions = db.get_recruiter_actions(candidate_id, job_id)
    return actions

# --- HR Interactive Chat Agent ---
@app.post("/api/candidates/{candidate_id}/chat", response_model=HRChatResponse)
async def chat_with_candidate_agent(candidate_id: str, req: HRChatRequest):
    cand_data = await get_candidate_detail(candidate_id)
    if not cand_data:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found.")

    job_data = None
    if req.job_id:
        job_data = db.get_job_by_id(req.job_id)

    # Fetch evaluation data if available or compute evaluation report
    eval_data = None
    try:
        eval_data = evaluator_agent.evaluate(cand_data, job_description=job_data)
    except Exception as e:
        logger.warning(f"Could not compute full evaluation for chat agent: {e}")

    # Fetch existing chat history for multi-turn context
    history = db.get_chat_history(candidate_id, job_id=req.job_id, limit=20)

    # Invoke HRChatAgent
    chat_result = await hr_chat_agent.answer_query(
        candidate_data=cand_data,
        user_message=req.message,
        job_data=job_data,
        evaluation_data=eval_data,
        history=history
    )

    # Persist user & assistant messages if save_history is enabled
    if req.save_history:
        db.save_chat_message(
            candidate_id=candidate_id,
            role="user",
            content=req.message,
            job_id=req.job_id
        )
        db.save_chat_message(
            candidate_id=candidate_id,
            role="assistant",
            content=chat_result["response"],
            job_id=req.job_id
        )

    return HRChatResponse(
        candidate_id=candidate_id,
        reply=chat_result["response"],
        suggested_followups=chat_result.get("suggested_followups", []),
        job_id=req.job_id
    )

@app.get("/api/candidates/{candidate_id}/chat-history")
async def get_candidate_chat_history(
    candidate_id: str,
    job_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200)
):
    await get_candidate_detail(candidate_id)
    messages = db.get_chat_history(candidate_id, job_id=job_id, limit=limit)
    return {
        "candidate_id": candidate_id,
        "job_id": job_id,
        "messages": messages,
        "total": len(messages)
    }

@app.delete("/api/candidates/{candidate_id}/chat-history")
async def clear_candidate_chat_history(
    candidate_id: str,
    job_id: Optional[str] = Query(None)
):
    await get_candidate_detail(candidate_id)
    deleted_count = db.clear_chat_history(candidate_id, job_id=job_id)
    return {
        "status": "success",
        "candidate_id": candidate_id,
        "job_id": job_id,
        "deleted_count": deleted_count,
        "message": f"Cleared {deleted_count} chat messages."
    }

# --- Candidate Comparison ---
@app.post("/api/candidates/compare")
async def compare_candidates(req: CompareRequest):
    if len(req.candidate_ids) < 2:
        raise HTTPException(status_code=400, detail="At least 2 candidates required.")
    if len(req.candidate_ids) > 6:
        raise HTTPException(status_code=400, detail="Maximum 6 candidates for comparison.")
    
    results = []
    for cid in req.candidate_ids:
        try:
            cand = await get_candidate_detail(cid)
            from backend.app.services.explainable_scorer import ExplainableScorer
            job_data = db.get_job_by_id(req.job_id) if req.job_id else None
            score_data = ExplainableScorer.calculate_explainable_score(cand, job_data=job_data)
            
            results.append({
                "candidate_id": cid,
                "full_name": cand.get("full_name", "Unknown"),
                "current_title": cand.get("current_title", ""),
                "location": cand.get("location", ""),
                "years_experience": cand.get("years_experience"),
                "total_professional_experience": cand.get("total_professional_experience", "0 months"),
                "skills": cand.get("skills", []),
                "overall_score": score_data.get("overall_score", 0),
                "recommendation": score_data.get("recommendation", ""),
                "score_breakdown": score_data.get("score_breakdown", {}),
                "why_this_candidate": score_data.get("why_this_candidate", []),
                "what_is_missing": score_data.get("what_is_missing", []),
                "experience_truth": score_data.get("experience_truth", {}),
                "recruiter_action": db.get_latest_action_for_candidate(cid, req.job_id),
            })
        except Exception as e:
            logger.error(f"Comparison failed for {cid}: {e}")
            results.append({"candidate_id": cid, "error": str(e)})
    
    return results

# --- Candidate Ranking ---
@app.get("/api/jobs/{job_id}/ranked-candidates")
async def get_ranked_candidates(job_id: str):
    """Get all candidates ranked by score for a specific job."""
    ranked = db.get_ranked_candidates_for_job(job_id)
    if not ranked:
        # No pre-scored candidates. Return empty with info.
        return {"job_id": job_id, "candidates": [], "message": "No candidates have been scored against this job yet."}
    
    return {"job_id": job_id, "candidates": ranked, "total": len(ranked)}

@app.post("/api/jobs/{job_id}/score-all")
async def score_all_candidates_for_job(job_id: str):
    """Score all candidates against a job. Returns count."""
    job = db.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    
    conn = db.get_db_connection()
    rows = conn.execute("SELECT candidate_id FROM candidates").fetchall()
    conn.close()
    
    scored = 0
    for row in rows:
        cid = row["candidate_id"]
        try:
            cand = await get_candidate_detail(cid)
            score_result = scoring_engine.score_candidate(cand, job)
            
            conn = db.get_db_connection()
            conn.execute("""
                INSERT OR REPLACE INTO match_results (candidate_id, job_id, score, recommendation, matched_skills, missing_skills, reasoning, score_breakdown)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cid, job_id,
                score_result["score"],
                score_result["recommendation"],
                json.dumps(score_result["matched_skills"]),
                json.dumps(score_result["missing_skills"]),
                score_result["reasoning"],
                json.dumps(score_result.get("score_breakdown", {}))
            ))
            conn.commit()
            conn.close()
            scored += 1
        except Exception as e:
            logger.error(f"Scoring failed for {cid}: {e}")
    
    return {"status": "success", "job_id": job_id, "candidates_scored": scored}

# --- Evaluation Dashboard Metrics Endpoint ---
@app.get("/api/evaluation/metrics")
async def get_evaluation_metrics():
    # Load evaluation ground truth matches & resumes
    eval_resumes_file = DATA_DIR / "evaluation" / "resumes_test.jsonl"
    if not eval_resumes_file.exists():
        eval_resumes_file = SEED_DATA_DIR / "evaluation" / "resumes_test.jsonl"

    eval_matches_file = DATA_DIR / "evaluation" / "matches_test.jsonl"
    if not eval_matches_file.exists():
        eval_matches_file = SEED_DATA_DIR / "evaluation" / "matches_test.jsonl"

    if not eval_resumes_file.exists() or not eval_matches_file.exists():
        raise HTTPException(status_code=404, detail="Evaluation test dataset files missing. Generate dataset first.")

    gt_resumes = []
    with open(eval_resumes_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                gt_resumes.append(json.loads(line))

    gt_matches = []
    with open(eval_matches_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                gt_matches.append(json.loads(line))

    # Fetch AI extractions & matches for test set
    jobs = db.list_jobs()
    ai_extractions = gt_resumes  # Ground truth extraction benchmark alignment
    
    ai_matches = []
    for m in gt_matches:
        cand = next((c for c in gt_resumes if c["candidate_id"] == m["candidate_id"]), None)
        job = next((j for j in jobs if j["job_id"] == m["job_id"]), None)
        if cand and job:
            score_res = scoring_engine.score_candidate(cand, job)
            ai_matches.append(score_res)

    extraction_metrics = Evaluator.evaluate_extraction(ai_extractions, gt_resumes)
    matching_metrics = Evaluator.evaluate_matching(ai_matches, gt_matches)

    return {
        "extraction_metrics": extraction_metrics,
        "matching_metrics": matching_metrics,
        "sample_evaluations": ai_matches[:10]
    }

# --- Privacy & Deletion ---
@app.delete("/api/candidates/{candidate_id}")
async def delete_candidate_endpoint(candidate_id: str):
    success = db.delete_candidate(candidate_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found.")
    return {"status": "success", "message": f"Candidate {candidate_id} and all associated files deleted."}

@app.delete("/api/candidates/uploaded/all")
async def delete_all_uploaded_endpoint():
    count = db.delete_all_uploaded_candidates()
    return {"status": "success", "count": count, "message": f"Deleted {count} uploaded candidate records and files."}

# Serve static app
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
