import os
import json
import sqlite3
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

_configured_db = os.getenv("DATABASE_PATH")
if _configured_db and _configured_db.strip():
    DB_PATH = Path(_configured_db.strip()).resolve()
elif Path("/app/local_data").exists():
    DB_PATH = Path("/app/local_data/cv_screening.db")
else:
    DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cv_screening.db"

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Candidates table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            candidate_id TEXT PRIMARY KEY,
            full_name TEXT,
            email TEXT,
            phone TEXT,
            location TEXT,
            roles TEXT,
            skills TEXT,
            years_experience REAL,
            notice_period TEXT,
            source TEXT DEFAULT 'UPLOADED',
            status TEXT DEFAULT 'COMPLETED',
            raw_json TEXT,
            file_hash TEXT,
            filename TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Original files table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS original_files (
            candidate_id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            sha256_hash TEXT NOT NULL UNIQUE,
            file_data BLOB NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Audit events table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            candidate_id TEXT,
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Match results table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS match_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            score REAL NOT NULL,
            recommendation TEXT NOT NULL,
            matched_skills TEXT,
            missing_skills TEXT,
            reasoning TEXT,
            score_breakdown TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(candidate_id, job_id)
        )
    """)

    # Jobs table (new)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            department TEXT DEFAULT '',
            location TEXT DEFAULT '',
            employment_type TEXT DEFAULT 'Full-time',
            seniority TEXT DEFAULT 'Mid-level',
            description TEXT DEFAULT '',
            minimum_years_experience REAL DEFAULT 0.0,
            required_skills TEXT DEFAULT '[]',
            preferred_skills TEXT DEFAULT '[]',
            education_requirements TEXT DEFAULT '[]',
            domain_requirements TEXT DEFAULT '[]',
            responsibilities TEXT DEFAULT '[]',
            other_constraints TEXT DEFAULT '',
            source TEXT DEFAULT 'MANUAL',
            status TEXT DEFAULT 'ACTIVE',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Recruiter actions table (new)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recruiter_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT NOT NULL,
            job_id TEXT,
            action TEXT NOT NULL,
            note TEXT DEFAULT '',
            tag TEXT DEFAULT '',
            user_id TEXT DEFAULT 'default',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Batch jobs table (new)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS batch_jobs (
            batch_id TEXT PRIMARY KEY,
            job_id TEXT,
            status TEXT DEFAULT 'QUEUED',
            total INTEGER DEFAULT 0,
            completed INTEGER DEFAULT 0,
            processing INTEGER DEFAULT 0,
            queued INTEGER DEFAULT 0,
            failed INTEGER DEFAULT 0,
            file_statuses TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Candidate chat messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS candidate_chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT NOT NULL,
            job_id TEXT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (candidate_id) REFERENCES candidates(candidate_id) ON DELETE CASCADE
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_cand ON candidate_chat_messages(candidate_id, created_at ASC)")

    # Ensure match_results table has score_breakdown column (migration helper)
    try:
        cursor.execute("SELECT score_breakdown FROM match_results LIMIT 1")
    except sqlite3.OperationalError:
        logger.info("Migrating database: adding 'score_breakdown' column to 'match_results' table.")
        cursor.execute("ALTER TABLE match_results ADD COLUMN score_breakdown TEXT")

    conn.commit()
    conn.close()

# --- Chat Messages Persistence ---
def save_chat_message(candidate_id: str, role: str, content: str, job_id: Optional[str] = None) -> int:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO candidate_chat_messages (candidate_id, job_id, role, content) VALUES (?, ?, ?, ?)",
        (candidate_id, job_id, role, content)
    )
    msg_id = cur.lastrowid
    conn.commit()
    conn.close()
    return msg_id

def get_chat_history(candidate_id: str, job_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    if job_id:
        rows = conn.execute(
            "SELECT id, candidate_id, job_id, role, content, created_at FROM candidate_chat_messages WHERE candidate_id = ? AND (job_id = ? OR job_id IS NULL) ORDER BY created_at ASC LIMIT ?",
            (candidate_id, job_id, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, candidate_id, job_id, role, content, created_at FROM candidate_chat_messages WHERE candidate_id = ? ORDER BY created_at ASC LIMIT ?",
            (candidate_id, limit)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def clear_chat_history(candidate_id: str, job_id: Optional[str] = None) -> int:
    conn = get_db_connection()
    cur = conn.cursor()
    if job_id:
        cur.execute("DELETE FROM candidate_chat_messages WHERE candidate_id = ? AND job_id = ?", (candidate_id, job_id))
    else:
        cur.execute("DELETE FROM candidate_chat_messages WHERE candidate_id = ?", (candidate_id,))
    count = cur.rowcount
    conn.commit()
    conn.close()
    return count

# --- Audit Logging ---
def log_audit_event(event_type: str, candidate_id: Optional[str] = None, details: str = ""):
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO audit_logs (event_type, candidate_id, details) VALUES (?, ?, ?)",
        (event_type, candidate_id, details)
    )
    conn.commit()
    conn.close()

# --- File Hashing ---
def calculate_sha256(content_bytes: bytes) -> str:
    return hashlib.sha256(content_bytes).hexdigest()

def check_duplicate_file(sha256_hash: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM original_files WHERE sha256_hash = ?", (sha256_hash,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

# --- Candidate CRUD ---
def get_candidate_by_id(candidate_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
    conn.close()
    if not row:
        return None
    item = dict(row)
    if item.get("raw_json"):
        try:
            return json.loads(item["raw_json"])
        except Exception:
            pass
    return item

def save_candidate_record(cand_data: Dict[str, Any], source: str = "UPLOADED", status: str = "COMPLETED", filename: str = "", file_hash: str = ""):
    conn = get_db_connection()
    cand_id = cand_data["candidate_id"]
    
    roles_str = json.dumps(cand_data.get("roles", []))
    skills_str = json.dumps(cand_data.get("skills", []))
    raw_json_str = json.dumps(cand_data)
    
    conn.execute("""
        INSERT OR REPLACE INTO candidates (
            candidate_id, full_name, email, phone, location, roles, skills,
            years_experience, notice_period, source, status, raw_json, file_hash, filename
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        cand_id,
        cand_data.get("full_name"),
        cand_data.get("email"),
        cand_data.get("phone"),
        cand_data.get("location"),
        roles_str,
        skills_str,
        cand_data.get("years_experience"),
        cand_data.get("notice_period"),
        source,
        status,
        raw_json_str,
        file_hash,
        filename
    ))
    
    conn.commit()
    conn.close()
    log_audit_event("SAVE_CANDIDATE", cand_id, f"Saved candidate record from source {source}")

def save_original_file(candidate_id: str, filename: str, file_type: str, sha256_hash: str, file_data: bytes):
    conn = get_db_connection()
    conn.execute("""
        INSERT OR REPLACE INTO original_files (candidate_id, filename, file_type, sha256_hash, file_data)
        VALUES (?, ?, ?, ?, ?)
    """, (candidate_id, filename, file_type, sha256_hash, file_data))
    conn.commit()
    conn.close()
    log_audit_event("SAVE_FILE", candidate_id, f"Stored original file {filename}")

def delete_candidate(candidate_id: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Delete from candidates table and track if record existed
    cursor.execute("DELETE FROM candidates WHERE candidate_id = ?", (candidate_id,))
    deleted = cursor.rowcount > 0
    
    # Delete associated original files
    cursor.execute("DELETE FROM original_files WHERE candidate_id = ?", (candidate_id,))
    if cursor.rowcount > 0:
        deleted = True
        
    cursor.execute("DELETE FROM match_results WHERE candidate_id = ?", (candidate_id,))
    cursor.execute("DELETE FROM recruiter_actions WHERE candidate_id = ?", (candidate_id,))
    cursor.execute("DELETE FROM candidate_chat_messages WHERE candidate_id = ?", (candidate_id,))
    
    conn.commit()
    conn.close()
    
    if deleted:
        log_audit_event("DELETE_CANDIDATE", candidate_id, "Candidate record and files removed")
    return deleted

def delete_all_uploaded_candidates() -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Select all UPLOADED IDs (case-insensitive)
    rows = cursor.execute("SELECT candidate_id FROM candidates WHERE UPPER(source) = 'UPLOADED'").fetchall()
    uploaded_ids = [r["candidate_id"] for r in rows]
    
    # Also include any in original_files that might not be in candidates
    orig_rows = cursor.execute("SELECT candidate_id FROM original_files").fetchall()
    for r in orig_rows:
        cid = r["candidate_id"]
        if cid not in uploaded_ids:
            cand_row = cursor.execute("SELECT source FROM candidates WHERE candidate_id = ?", (cid,)).fetchone()
            if not cand_row or (cand_row["source"] and cand_row["source"].upper() == "UPLOADED"):
                uploaded_ids.append(cid)
    
    for cid in uploaded_ids:
        cursor.execute("DELETE FROM candidates WHERE candidate_id = ?", (cid,))
        cursor.execute("DELETE FROM original_files WHERE candidate_id = ?", (cid,))
        cursor.execute("DELETE FROM match_results WHERE candidate_id = ?", (cid,))
        cursor.execute("DELETE FROM recruiter_actions WHERE candidate_id = ?", (cid,))
        cursor.execute("DELETE FROM candidate_chat_messages WHERE candidate_id = ?", (cid,))
        
    count = len(uploaded_ids)
    conn.commit()
    conn.close()
    
    log_audit_event("DELETE_ALL_UPLOADED", None, f"Deleted {count} uploaded candidates")
    return count

# --- Job CRUD ---
def save_job(job_data: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_db_connection()
    job_id = job_data.get("job_id", f"JOB-{hashlib.md5(str(datetime.utcnow()).encode()).hexdigest()[:8].upper()}")
    
    conn.execute("""
        INSERT OR REPLACE INTO jobs (
            job_id, title, department, location, employment_type, seniority,
            description, minimum_years_experience, required_skills, preferred_skills,
            education_requirements, domain_requirements, responsibilities,
            other_constraints, source, status, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job_id,
        job_data.get("title", ""),
        job_data.get("department", ""),
        job_data.get("location", ""),
        job_data.get("employment_type", "Full-time"),
        job_data.get("seniority", "Mid-level"),
        job_data.get("description", ""),
        float(job_data.get("minimum_years_experience", 0)),
        json.dumps(job_data.get("required_skills", job_data.get("mandatory_skills", []))),
        json.dumps(job_data.get("preferred_skills", [])),
        json.dumps(job_data.get("education_requirements", [])),
        json.dumps(job_data.get("domain_requirements", [])),
        json.dumps(job_data.get("responsibilities", [])),
        job_data.get("other_constraints", ""),
        job_data.get("source", "MANUAL"),
        job_data.get("status", "ACTIVE"),
        datetime.utcnow().isoformat()
    ))
    conn.commit()
    conn.close()
    
    log_audit_event("SAVE_JOB", None, f"Saved job {job_id}: {job_data.get('title', '')}")
    job_data["job_id"] = job_id
    return job_data

def get_job_by_id(job_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    conn.close()
    if not row:
        return None
    item = dict(row)
    for field in ["required_skills", "preferred_skills", "education_requirements", "domain_requirements", "responsibilities"]:
        if item.get(field):
            try:
                item[field] = json.loads(item[field])
            except Exception:
                item[field] = []
    # Alias for backward compatibility
    item["mandatory_skills"] = item.get("required_skills", [])
    return item

def list_jobs(status: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    if status:
        rows = conn.execute("SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC", (status,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
    conn.close()
    
    results = []
    for row in rows:
        item = dict(row)
        for field in ["required_skills", "preferred_skills", "education_requirements", "domain_requirements", "responsibilities"]:
            if item.get(field):
                try:
                    item[field] = json.loads(item[field])
                except Exception:
                    item[field] = []
        item["mandatory_skills"] = item.get("required_skills", [])
        results.append(item)
    return results

def delete_job(job_id: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
    deleted = cursor.rowcount > 0
    cursor.execute("DELETE FROM match_results WHERE job_id = ?", (job_id,))
    conn.commit()
    conn.close()
    if deleted:
        log_audit_event("DELETE_JOB", None, f"Deleted job {job_id}")
    return deleted

# --- Recruiter Actions ---
def save_recruiter_action(candidate_id: str, action: str, job_id: Optional[str] = None, note: str = "", tag: str = "", user_id: str = "default"):
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO recruiter_actions (candidate_id, job_id, action, note, tag, user_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (candidate_id, job_id, action, note, tag, user_id))
    conn.commit()
    conn.close()
    log_audit_event("RECRUITER_ACTION", candidate_id, f"Action: {action}, Job: {job_id}, Note: {note}")

def get_recruiter_actions(candidate_id: str, job_id: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    if job_id:
        rows = conn.execute(
            "SELECT * FROM recruiter_actions WHERE candidate_id = ? AND job_id = ? ORDER BY created_at DESC",
            (candidate_id, job_id)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM recruiter_actions WHERE candidate_id = ? ORDER BY created_at DESC",
            (candidate_id,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_latest_action_for_candidate(candidate_id: str, job_id: Optional[str] = None) -> Optional[str]:
    conn = get_db_connection()
    if job_id:
        row = conn.execute(
            "SELECT action FROM recruiter_actions WHERE candidate_id = ? AND job_id = ? ORDER BY created_at DESC LIMIT 1",
            (candidate_id, job_id)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT action FROM recruiter_actions WHERE candidate_id = ? ORDER BY created_at DESC LIMIT 1",
            (candidate_id,)
        ).fetchone()
    conn.close()
    return row["action"] if row else None

# --- Batch Jobs ---
def save_batch_job(batch_id: str, job_id: Optional[str], total: int, file_statuses: list):
    conn = get_db_connection()
    conn.execute("""
        INSERT OR REPLACE INTO batch_jobs (batch_id, job_id, status, total, queued, file_statuses)
        VALUES (?, ?, 'QUEUED', ?, ?, ?)
    """, (batch_id, job_id, total, total, json.dumps(file_statuses)))
    conn.commit()
    conn.close()

def update_batch_job(batch_id: str, updates: Dict[str, Any]):
    conn = get_db_connection()
    set_clauses = []
    values = []
    for k, v in updates.items():
        if k in ("status", "completed", "processing", "queued", "failed", "file_statuses"):
            set_clauses.append(f"{k} = ?")
            values.append(json.dumps(v) if k == "file_statuses" else v)
    set_clauses.append("updated_at = ?")
    values.append(datetime.utcnow().isoformat())
    values.append(batch_id)
    
    if set_clauses:
        conn.execute(f"UPDATE batch_jobs SET {', '.join(set_clauses)} WHERE batch_id = ?", values)
        conn.commit()
    conn.close()

def get_batch_job(batch_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM batch_jobs WHERE batch_id = ?", (batch_id,)).fetchone()
    conn.close()
    if not row:
        return None
    item = dict(row)
    if item.get("file_statuses"):
        try:
            item["file_statuses"] = json.loads(item["file_statuses"])
        except Exception:
            item["file_statuses"] = []
    return item

# --- Dashboard Metrics ---
def get_dashboard_metrics(job_id: Optional[str] = None) -> Dict[str, Any]:
    conn = get_db_connection()
    
    total_candidates = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
    uploaded_count = conn.execute("SELECT COUNT(*) FROM candidates WHERE source = 'UPLOADED'").fetchone()[0]
    mock_count = conn.execute("SELECT COUNT(*) FROM candidates WHERE source = 'MOCK'").fetchone()[0]
    
    total_jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    active_jobs = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'ACTIVE'").fetchone()[0]
    
    # Match statistics
    if job_id:
        match_rows = conn.execute(
            "SELECT score, recommendation FROM match_results WHERE job_id = ?", (job_id,)
        ).fetchall()
    else:
        match_rows = conn.execute("SELECT score, recommendation FROM match_results").fetchall()
    
    strong_matches = sum(1 for r in match_rows if r["score"] >= 85)
    matches = sum(1 for r in match_rows if 70 <= r["score"] < 85)
    needs_review = sum(1 for r in match_rows if 50 <= r["score"] < 70)
    not_matched = sum(1 for r in match_rows if r["score"] < 50)
    
    # Score distribution
    score_dist = {"90-100": 0, "80-89": 0, "70-79": 0, "60-69": 0, "50-59": 0, "below-50": 0}
    for r in match_rows:
        s = r["score"]
        if s >= 90: score_dist["90-100"] += 1
        elif s >= 80: score_dist["80-89"] += 1
        elif s >= 70: score_dist["70-79"] += 1
        elif s >= 60: score_dist["60-69"] += 1
        elif s >= 50: score_dist["50-59"] += 1
        else: score_dist["below-50"] += 1
    
    # Recruiter action stats
    shortlisted = conn.execute("SELECT COUNT(DISTINCT candidate_id) FROM recruiter_actions WHERE action = 'SHORTLIST'").fetchone()[0]
    rejected = conn.execute("SELECT COUNT(DISTINCT candidate_id) FROM recruiter_actions WHERE action = 'REJECT'").fetchone()[0]
    interview_count = conn.execute("SELECT COUNT(DISTINCT candidate_id) FROM recruiter_actions WHERE action = 'INTERVIEW'").fetchone()[0]
    
    conn.close()
    
    return {
        "total_candidates": total_candidates,
        "uploaded_candidates": uploaded_count,
        "mock_candidates": mock_count,
        "total_jobs": total_jobs,
        "active_jobs": active_jobs,
        "total_screened": len(match_rows),
        "strong_matches": strong_matches,
        "matches": matches,
        "needs_review": needs_review,
        "not_matched": not_matched,
        "shortlisted": shortlisted,
        "rejected": rejected,
        "interview_recommended": interview_count,
        "score_distribution": score_dist
    }

# --- Match Results ---
def get_match_result(candidate_id: str, job_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM match_results WHERE candidate_id = ? AND job_id = ?",
        (candidate_id, job_id)
    ).fetchone()
    conn.close()
    if not row:
        return None
    item = dict(row)
    for field in ["matched_skills", "missing_skills", "score_breakdown"]:
        if item.get(field):
            try:
                item[field] = json.loads(item[field])
            except Exception:
                pass
    return item

def get_ranked_candidates_for_job(job_id: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT m.*, c.full_name, c.location, c.roles, c.skills, c.years_experience, c.source, c.status as cand_status
        FROM match_results m
        JOIN candidates c ON m.candidate_id = c.candidate_id
        WHERE m.job_id = ?
        ORDER BY m.score DESC
    """, (job_id,)).fetchall()
    conn.close()
    
    results = []
    for r in rows:
        item = dict(r)
        for field in ["matched_skills", "missing_skills", "roles", "skills", "score_breakdown"]:
            if item.get(field):
                try:
                    item[field] = json.loads(item[field])
                except Exception:
                    pass
        results.append(item)
    return results

init_db()
