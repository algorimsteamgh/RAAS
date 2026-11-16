"""PostgreSQL data access (psycopg 3 with a connection pool).

Function names and return shapes are the same as the SQLite version, so the
API responses do not change: JSON columns come back as Python lists/dicts and
timestamps as "YYYY-MM-DD HH:MM:SS" (UTC) strings, as SQLite returned them.

The schema is owned by Alembic (backend/app/db/migrations); see
docs/aws/DATABASE_SCHEMA.md for the table reference.
"""
import hashlib
import json
import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from backend.app.config import settings

logger = logging.getLogger(__name__)

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

# ----------------------------------------------------------------------------
# Connections
# ----------------------------------------------------------------------------
_pool: Optional[ConnectionPool] = None
_pool_lock = threading.Lock()
_secret_cache: Dict[str, str] = {}
_secret_lock = threading.Lock()


def _secret_credentials(refresh: bool = False) -> Dict[str, str]:
    """Username/password from the RDS-managed secret (DATABASE_SECRET_ARN)."""
    with _secret_lock:
        if refresh or not _secret_cache:
            import boto3

            client = boto3.client("secretsmanager", region_name=settings.AWS_REGION)
            value = json.loads(client.get_secret_value(SecretId=settings.DATABASE_SECRET_ARN)["SecretString"])
            _secret_cache.clear()
            _secret_cache.update({"user": value["username"], "password": value["password"]})
        return dict(_secret_cache)


def _connect_kwargs(refresh_secret: bool = False) -> Dict[str, Any]:
    if settings.DATABASE_URL:
        return {"conninfo": settings.DATABASE_URL}
    kwargs: Dict[str, Any] = {
        "host": settings.DATABASE_HOST,
        "port": settings.DATABASE_PORT,
        "dbname": settings.DATABASE_NAME,
        "user": settings.DATABASE_USER,
        "sslmode": settings.DATABASE_SSLMODE,
        "connect_timeout": settings.DB_CONNECT_TIMEOUT_SECONDS,
        "application_name": "raashiring",
    }
    if settings.DATABASE_SECRET_ARN:
        kwargs.update(_secret_credentials(refresh=refresh_secret))
    elif settings.DATABASE_PASSWORD:
        kwargs["password"] = settings.DATABASE_PASSWORD
    return kwargs


def _is_auth_failure(err: Exception) -> bool:
    return "password authentication failed" in str(err).lower()


def _connect_with_rotation(connect: Any, **extra: Any) -> Any:
    """Open one connection with `connect(conninfo, **kwargs)`. When the
    credentials come from Secrets Manager and the login fails, the secret is
    re-read once (it may have been rotated) and the login retried."""
    kwargs = _connect_kwargs()
    conninfo = kwargs.pop("conninfo", "")
    try:
        return connect(conninfo, **kwargs, **extra)
    except psycopg.OperationalError as err:
        if settings.DATABASE_SECRET_ARN and _is_auth_failure(err):
            logger.warning("Database login failed; re-reading the credentials secret (rotation).")
            kwargs = _connect_kwargs(refresh_secret=True)
            conninfo = kwargs.pop("conninfo", "")
            return connect(conninfo, **kwargs, **extra)
        raise


def raw_connect(**extra: Any) -> psycopg.Connection:
    """A standalone (unpooled) connection."""
    return _connect_with_rotation(psycopg.Connection.connect, **extra)


class _PoolConnection(psycopg.Connection):
    """Connection class for the pool: credentials are resolved on every new
    connection, so a rotated password is picked up without a restart."""

    @classmethod
    def connect(cls, conninfo: str = "", **kwargs: Any) -> "_PoolConnection":  # type: ignore[override]
        parent = super(_PoolConnection, cls).connect
        return _connect_with_rotation(parent, row_factory=dict_row)


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ConnectionPool(
                    conninfo="",
                    connection_class=_PoolConnection,
                    min_size=settings.DB_POOL_MIN_SIZE,
                    max_size=settings.DB_POOL_MAX_SIZE,
                    timeout=30,
                    max_idle=300,
                    check=ConnectionPool.check_connection,
                    open=True,
                    name="raas",
                )
    return _pool


def close_pool() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    """A pooled connection with dict rows. Commits when the block succeeds,
    rolls back when it raises."""
    with get_pool().connection() as conn:
        yield conn


def get_db_connection() -> psycopg.Connection:
    """Backward-compatible helper: a standalone connection with dict rows.
    Prefer `with connection() as conn:` (pooled)."""
    return raw_connect(row_factory=dict_row)


def ping() -> bool:
    try:
        with connection() as conn:
            conn.execute("SELECT 1").fetchone()
        return True
    except Exception as err:  # pragma: no cover - depends on infrastructure
        logger.warning("Database ping failed: %s", err)
        return False


def init_db() -> None:
    """Bring the schema to the latest Alembic revision (local runs and tests).
    In production the migrate ECS task does this before each deploy."""
    from backend.app.db.migrate import upgrade

    upgrade()


# ----------------------------------------------------------------------------
# Value helpers
# ----------------------------------------------------------------------------
def strip_nul(value: Any) -> Any:
    """PostgreSQL text and jsonb cannot hold NUL characters (SQLite could).
    PDF text extraction occasionally produces them; drop them on write."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [strip_nul(v) for v in value]
    if isinstance(value, dict):
        return {strip_nul(k): strip_nul(v) for k, v in value.items()}
    return value


def _json(value: Any) -> Optional[Jsonb]:
    if value is None:
        return None
    return Jsonb(strip_nul(value))


def _format_ts(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.strftime(TIMESTAMP_FORMAT)
    return value


def _row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return {k: _format_ts(v) for k, v in row.items()}


def _rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [_row(r) for r in rows]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ----------------------------------------------------------------------------
# Chat messages
# ----------------------------------------------------------------------------
def save_chat_message(candidate_id: str, role: str, content: str, job_id: Optional[str] = None) -> int:
    with connection() as conn:
        row = conn.execute(
            "INSERT INTO candidate_chat_messages (candidate_id, job_id, role, content) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (candidate_id, job_id, role, strip_nul(content)),
        ).fetchone()
    return row["id"]


def get_chat_history(candidate_id: str, job_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    with connection() as conn:
        if job_id:
            rows = conn.execute(
                "SELECT id, candidate_id, job_id, role, content, created_at FROM candidate_chat_messages "
                "WHERE candidate_id = %s AND (job_id = %s OR job_id IS NULL) ORDER BY created_at ASC, id ASC LIMIT %s",
                (candidate_id, job_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, candidate_id, job_id, role, content, created_at FROM candidate_chat_messages "
                "WHERE candidate_id = %s ORDER BY created_at ASC, id ASC LIMIT %s",
                (candidate_id, limit),
            ).fetchall()
    return _rows(rows)


def clear_chat_history(candidate_id: str, job_id: Optional[str] = None) -> int:
    with connection() as conn:
        if job_id:
            cur = conn.execute(
                "DELETE FROM candidate_chat_messages WHERE candidate_id = %s AND job_id = %s", (candidate_id, job_id)
            )
        else:
            cur = conn.execute("DELETE FROM candidate_chat_messages WHERE candidate_id = %s", (candidate_id,))
        return cur.rowcount


# ----------------------------------------------------------------------------
# Audit log
# ----------------------------------------------------------------------------
def log_audit_event(event_type: str, candidate_id: Optional[str] = None, details: str = "", conn: Optional[psycopg.Connection] = None):
    sql = "INSERT INTO audit_logs (event_type, candidate_id, details) VALUES (%s, %s, %s)"
    params = (event_type, candidate_id, strip_nul(details))
    if conn is not None:
        conn.execute(sql, params)
        return
    with connection() as own:
        own.execute(sql, params)


# ----------------------------------------------------------------------------
# Files
# ----------------------------------------------------------------------------
def calculate_sha256(content_bytes: bytes) -> str:
    return hashlib.sha256(content_bytes).hexdigest()


def check_duplicate_file(sha256_hash: str) -> Optional[Dict[str, Any]]:
    with connection() as conn:
        row = conn.execute("SELECT * FROM original_files WHERE sha256_hash = %s", (sha256_hash,)).fetchone()
    return _row(row)


def get_original_file(candidate_id: str) -> Optional[Dict[str, Any]]:
    """Metadata of a candidate's original CV (the bytes are in CV storage)."""
    with connection() as conn:
        row = conn.execute("SELECT * FROM original_files WHERE candidate_id = %s", (candidate_id,)).fetchone()
    return _row(row)


def save_original_file(candidate_id: str, filename: str, file_type: str, sha256_hash: str, s3_key: str, size_bytes: Optional[int] = None):
    with connection() as conn:
        # Same outcome as SQLite's INSERT OR REPLACE, which also removed a row of
        # another candidate holding the same hash (upload with "keep_both").
        displaced = conn.execute(
            "DELETE FROM original_files WHERE sha256_hash = %s AND candidate_id <> %s RETURNING s3_key",
            (sha256_hash, candidate_id),
        ).fetchall()
        conn.execute(
            """
            INSERT INTO original_files (candidate_id, filename, file_type, sha256_hash, s3_key, size_bytes)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (candidate_id) DO UPDATE SET
                filename = EXCLUDED.filename, file_type = EXCLUDED.file_type,
                sha256_hash = EXCLUDED.sha256_hash, s3_key = EXCLUDED.s3_key,
                size_bytes = EXCLUDED.size_bytes, created_at = now()
            """,
            (candidate_id, strip_nul(filename), file_type, sha256_hash, s3_key, size_bytes),
        )
        log_audit_event("SAVE_FILE", candidate_id, f"Stored original file {strip_nul(filename)}", conn=conn)
    _delete_cv_objects([r["s3_key"] for r in displaced if r["s3_key"] != s3_key])


# ----------------------------------------------------------------------------
# Candidates
# ----------------------------------------------------------------------------
def count_candidates() -> int:
    with connection() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM candidates").fetchone()["n"]


def get_candidate_row(candidate_id: str) -> Optional[Dict[str, Any]]:
    with connection() as conn:
        row = conn.execute("SELECT * FROM candidates WHERE candidate_id = %s", (candidate_id,)).fetchone()
    return _row(row)


def get_candidate_by_id(candidate_id: str) -> Optional[Dict[str, Any]]:
    """The stored extraction (raw_json) when present, otherwise the row."""
    item = get_candidate_row(candidate_id)
    if not item:
        return None
    if isinstance(item.get("raw_json"), dict):
        return item["raw_json"]
    return item


def list_candidates(source: Optional[str] = None) -> List[Dict[str, Any]]:
    """Candidates, newest first, with each one's latest recruiter action."""
    sql = """
        SELECT c.*, la.action AS recruiter_action
        FROM candidates c
        LEFT JOIN LATERAL (
            SELECT r.action FROM recruiter_actions r
            WHERE r.candidate_id = c.candidate_id
            ORDER BY r.created_at DESC, r.id DESC LIMIT 1
        ) la ON true
    """
    params: tuple = ()
    if source:
        sql += " WHERE c.source = %s"
        params = (source,)
    sql += " ORDER BY c.created_at DESC, c.candidate_id"
    with connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return _rows(rows)


def list_candidate_payloads() -> List[Dict[str, Any]]:
    """candidate_id + parsed raw_json for every candidate (bulk scoring)."""
    with connection() as conn:
        rows = conn.execute("SELECT candidate_id, raw_json FROM candidates ORDER BY candidate_id").fetchall()
    return [dict(r) for r in rows]


def save_candidate_record(cand_data: Dict[str, Any], source: str = "UPLOADED", status: str = "COMPLETED", filename: str = "", file_hash: str = ""):
    cand_id = cand_data["candidate_id"]
    years = cand_data.get("years_experience")
    try:
        years = float(years) if years is not None else None
    except (TypeError, ValueError):
        years = None
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO candidates (
                candidate_id, full_name, email, phone, location, roles, skills,
                years_experience, notice_period, source, status, raw_json, file_hash, filename
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (candidate_id) DO UPDATE SET
                full_name = EXCLUDED.full_name, email = EXCLUDED.email, phone = EXCLUDED.phone,
                location = EXCLUDED.location, roles = EXCLUDED.roles, skills = EXCLUDED.skills,
                years_experience = EXCLUDED.years_experience, notice_period = EXCLUDED.notice_period,
                source = EXCLUDED.source, status = EXCLUDED.status, raw_json = EXCLUDED.raw_json,
                file_hash = EXCLUDED.file_hash, filename = EXCLUDED.filename, created_at = now()
            """,
            (
                cand_id,
                strip_nul(cand_data.get("full_name")),
                strip_nul(cand_data.get("email")),
                strip_nul(cand_data.get("phone")),
                strip_nul(cand_data.get("location")),
                _json(cand_data.get("roles", [])),
                _json(cand_data.get("skills", [])),
                years,
                strip_nul(cand_data.get("notice_period")),
                source,
                status,
                _json(cand_data),
                file_hash,
                strip_nul(filename),
            ),
        )
        log_audit_event("SAVE_CANDIDATE", cand_id, f"Saved candidate record from source {source}", conn=conn)


def _delete_candidate_rows(conn: psycopg.Connection, candidate_id: str) -> bool:
    deleted = conn.execute("DELETE FROM candidates WHERE candidate_id = %s", (candidate_id,)).rowcount > 0
    if conn.execute("DELETE FROM original_files WHERE candidate_id = %s", (candidate_id,)).rowcount > 0:
        deleted = True
    conn.execute("DELETE FROM match_results WHERE candidate_id = %s", (candidate_id,))
    conn.execute("DELETE FROM recruiter_actions WHERE candidate_id = %s", (candidate_id,))
    conn.execute("DELETE FROM candidate_chat_messages WHERE candidate_id = %s", (candidate_id,))
    return deleted


def _cv_keys_for(conn: psycopg.Connection, candidate_ids: List[str]) -> List[str]:
    if not candidate_ids:
        return []
    rows = conn.execute("SELECT s3_key FROM original_files WHERE candidate_id = ANY(%s)", (candidate_ids,)).fetchall()
    return [r["s3_key"] for r in rows if r["s3_key"]]


def _delete_cv_objects(keys: List[str]) -> None:
    if not keys:
        return
    from backend.app.services.cv_storage import get_cv_storage

    storage = get_cv_storage()
    for key in keys:
        try:
            storage.delete(key)
        except Exception as err:  # the database delete stands; the object is reported
            logger.error("Could not delete CV object %s: %s", key, err)


def delete_candidate(candidate_id: str) -> bool:
    with connection() as conn:
        keys = _cv_keys_for(conn, [candidate_id])
        deleted = _delete_candidate_rows(conn, candidate_id)
        if deleted:
            log_audit_event("DELETE_CANDIDATE", candidate_id, "Candidate record and files removed", conn=conn)
    _delete_cv_objects(keys)
    return deleted


def delete_all_uploaded_candidates() -> int:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT candidate_id FROM candidates WHERE UPPER(source) = 'UPLOADED'
            UNION
            SELECT f.candidate_id FROM original_files f
            LEFT JOIN candidates c ON c.candidate_id = f.candidate_id
            WHERE c.candidate_id IS NULL OR UPPER(c.source) = 'UPLOADED'
            """
        ).fetchall()
        uploaded_ids = [r["candidate_id"] for r in rows]
        keys = _cv_keys_for(conn, uploaded_ids)
        for cid in uploaded_ids:
            _delete_candidate_rows(conn, cid)
        log_audit_event("DELETE_ALL_UPLOADED", None, f"Deleted {len(uploaded_ids)} uploaded candidates", conn=conn)
    _delete_cv_objects(keys)
    return len(uploaded_ids)


# ----------------------------------------------------------------------------
# Jobs
# ----------------------------------------------------------------------------
_JOB_JSON_FIELDS = ["required_skills", "preferred_skills", "education_requirements", "domain_requirements", "responsibilities"]

# Demo pool sizes shown on the job cards (unchanged from the SQLite version).
JOB_POOLS = {
    "JOB-001": 128, "JOB-002": 96, "JOB-003": 82, "JOB-004": 114, "JOB-005": 80,
    "JOB-006": 92, "JOB-007": 64, "JOB-008": 75, "JOB-009": 110, "JOB-010": 85,
}


def count_jobs() -> int:
    with connection() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"]


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def save_job(job_data: Dict[str, Any]) -> Dict[str, Any]:
    job_id = job_data.get("job_id") or f"JOB-{hashlib.md5(str(utcnow()).encode()).hexdigest()[:8].upper()}"
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                job_id, title, department, location, employment_type, seniority,
                description, minimum_years_experience, required_skills, preferred_skills,
                education_requirements, domain_requirements, responsibilities,
                other_constraints, source, status, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (job_id) DO UPDATE SET
                title = EXCLUDED.title, department = EXCLUDED.department, location = EXCLUDED.location,
                employment_type = EXCLUDED.employment_type, seniority = EXCLUDED.seniority,
                description = EXCLUDED.description, minimum_years_experience = EXCLUDED.minimum_years_experience,
                required_skills = EXCLUDED.required_skills, preferred_skills = EXCLUDED.preferred_skills,
                education_requirements = EXCLUDED.education_requirements,
                domain_requirements = EXCLUDED.domain_requirements, responsibilities = EXCLUDED.responsibilities,
                other_constraints = EXCLUDED.other_constraints, source = EXCLUDED.source,
                status = EXCLUDED.status, updated_at = now()
            """,
            (
                job_id,
                strip_nul(job_data.get("title", "")),
                strip_nul(job_data.get("department", "")),
                strip_nul(job_data.get("location", "")),
                job_data.get("employment_type", "Full-time"),
                job_data.get("seniority", "Mid-level"),
                strip_nul(job_data.get("description", "")),
                float(job_data.get("minimum_years_experience", 0) or 0),
                _json(job_data.get("required_skills", job_data.get("mandatory_skills", []))),
                _json(job_data.get("preferred_skills", [])),
                _json(job_data.get("education_requirements", [])),
                _json(job_data.get("domain_requirements", [])),
                _json(job_data.get("responsibilities", [])),
                strip_nul(job_data.get("other_constraints", "")),
                job_data.get("source", "MANUAL"),
                job_data.get("status", "ACTIVE"),
            ),
        )
        log_audit_event("SAVE_JOB", None, f"Saved job {job_id}: {job_data.get('title', '')}", conn=conn)
    job_data["job_id"] = job_id
    return job_data


def _job_item(row: Dict[str, Any]) -> Dict[str, Any]:
    item = _row(row)
    for field in _JOB_JSON_FIELDS:
        item[field] = _as_list(item.get(field))
    item["mandatory_skills"] = item.get("required_skills", [])
    return item


def get_job_by_id(job_id: str) -> Optional[Dict[str, Any]]:
    with connection() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id = %s", (job_id,)).fetchone()
    return _job_item(row) if row else None


def list_jobs(status: Optional[str] = None) -> List[Dict[str, Any]]:
    order = " ORDER BY CASE WHEN job_id LIKE 'JOB-00%%' THEN 0 ELSE 1 END, job_id ASC, created_at DESC"
    with connection() as conn:
        if status:
            rows = conn.execute("SELECT * FROM jobs WHERE status = %s" + order, (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM jobs" + order).fetchall()
    results = []
    for row in rows:
        item = _job_item(row)
        item["candidate_count"] = JOB_POOLS.get(item.get("job_id", ""), 64)
        results.append(item)
    return results


def delete_job(job_id: str) -> bool:
    with connection() as conn:
        deleted = conn.execute("DELETE FROM jobs WHERE job_id = %s", (job_id,)).rowcount > 0
        conn.execute("DELETE FROM match_results WHERE job_id = %s", (job_id,))
        if deleted:
            log_audit_event("DELETE_JOB", None, f"Deleted job {job_id}", conn=conn)
    return deleted


# ----------------------------------------------------------------------------
# Recruiter actions
# ----------------------------------------------------------------------------
def save_recruiter_action(candidate_id: str, action: str, job_id: Optional[str] = None, note: str = "", tag: str = "", user_id: str = "default"):
    with connection() as conn:
        conn.execute(
            "INSERT INTO recruiter_actions (candidate_id, job_id, action, note, tag, user_id) VALUES (%s, %s, %s, %s, %s, %s)",
            (candidate_id, job_id, action, strip_nul(note), strip_nul(tag), user_id),
        )
        log_audit_event("RECRUITER_ACTION", candidate_id, f"Action: {action}, Job: {job_id}, Note: {note}", conn=conn)


def get_recruiter_actions(candidate_id: str, job_id: Optional[str] = None) -> List[Dict[str, Any]]:
    with connection() as conn:
        if job_id:
            rows = conn.execute(
                "SELECT * FROM recruiter_actions WHERE candidate_id = %s AND job_id = %s ORDER BY created_at DESC, id DESC",
                (candidate_id, job_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM recruiter_actions WHERE candidate_id = %s ORDER BY created_at DESC, id DESC",
                (candidate_id,),
            ).fetchall()
    return _rows(rows)


def get_latest_action_for_candidate(candidate_id: str, job_id: Optional[str] = None) -> Optional[str]:
    with connection() as conn:
        if job_id:
            row = conn.execute(
                "SELECT action FROM recruiter_actions WHERE candidate_id = %s AND job_id = %s ORDER BY created_at DESC, id DESC LIMIT 1",
                (candidate_id, job_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT action FROM recruiter_actions WHERE candidate_id = %s ORDER BY created_at DESC, id DESC LIMIT 1",
                (candidate_id,),
            ).fetchone()
    return row["action"] if row else None


# ----------------------------------------------------------------------------
# Batch jobs (progress lives here so it works across API and worker tasks)
# ----------------------------------------------------------------------------
BATCH_TERMINAL = ("COMPLETED", "FAILED", "SKIPPED")


def create_batch(batch_id: str, job_id: Optional[str], files: List[Dict[str, Any]]) -> None:
    """files: [{file_index, filename, file_type, staging_key, size_bytes, status?, error?}]"""
    with connection() as conn:
        conn.execute(
            "INSERT INTO batch_jobs (batch_id, job_id, status, total, queued) VALUES (%s, %s, 'QUEUED', %s, %s)",
            (batch_id, job_id, len(files), len(files)),
        )
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO batch_files (batch_id, file_index, filename, file_type, staging_key, size_bytes, status, error)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        batch_id, f["file_index"], strip_nul(f["filename"]), f["file_type"], f.get("staging_key"),
                        f.get("size_bytes"), f.get("status", "QUEUED"), f.get("error"),
                    )
                    for f in files
                ],
            )
        _refresh_batch_counts(conn, batch_id)


def _refresh_batch_counts(conn: psycopg.Connection, batch_id: str) -> None:
    conn.execute(
        """
        UPDATE batch_jobs b SET
            total = s.total, completed = s.completed, processing = s.processing,
            queued = s.queued, failed = s.failed,
            file_statuses = s.files,
            status = CASE WHEN s.total = s.completed + s.failed THEN 'COMPLETE'
                          WHEN s.processing > 0 OR s.completed + s.failed > 0 THEN 'PROCESSING'
                          ELSE 'QUEUED' END,
            updated_at = now()
        FROM (
            SELECT COUNT(*)::int AS total,
                   COUNT(*) FILTER (WHERE status IN ('COMPLETED', 'SKIPPED'))::int AS completed,
                   COUNT(*) FILTER (WHERE status = 'PROCESSING')::int AS processing,
                   COUNT(*) FILTER (WHERE status = 'QUEUED')::int AS queued,
                   COUNT(*) FILTER (WHERE status = 'FAILED')::int AS failed,
                   COALESCE(jsonb_agg(jsonb_build_object(
                       'filename', filename, 'status', status,
                       'candidate_id', CASE WHEN status = 'COMPLETED' THEN candidate_id END,
                       'error', error) ORDER BY file_index), '[]'::jsonb) AS files
            FROM batch_files WHERE batch_id = %s
        ) s
        WHERE b.batch_id = %s
        """,
        (batch_id, batch_id),
    )


def claim_batch_file(batch_id: str, file_index: int, candidate_id: str) -> Optional[Dict[str, Any]]:
    """Mark a file PROCESSING and return it, or None when it already reached a
    final state (a redelivered SQS message). The candidate id is fixed on the
    first attempt so a retry reuses it."""
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE batch_files SET status = 'PROCESSING', attempts = attempts + 1,
                candidate_id = COALESCE(candidate_id, %s), updated_at = now()
            WHERE batch_id = %s AND file_index = %s AND status NOT IN ('COMPLETED', 'FAILED', 'SKIPPED')
            RETURNING *
            """,
            (candidate_id, batch_id, file_index),
        ).fetchone()
        if row:
            _refresh_batch_counts(conn, batch_id)
    return dict(row) if row else None


def finish_batch_file(batch_id: str, file_index: int, status: str, error: Optional[str] = None, candidate_id: Optional[str] = None) -> None:
    with connection() as conn:
        conn.execute(
            """
            UPDATE batch_files SET status = %s, error = %s,
                candidate_id = COALESCE(%s, candidate_id), updated_at = now()
            WHERE batch_id = %s AND file_index = %s
            """,
            (status, strip_nul(error) if error else None, candidate_id, batch_id, file_index),
        )
        _refresh_batch_counts(conn, batch_id)


def requeue_batch_file(batch_id: str, file_index: int, error: str) -> None:
    """A retryable failure: back to QUEUED until SQS redelivers it."""
    with connection() as conn:
        conn.execute(
            "UPDATE batch_files SET status = 'QUEUED', error = %s, updated_at = now() WHERE batch_id = %s AND file_index = %s",
            (strip_nul(error), batch_id, file_index),
        )
        _refresh_batch_counts(conn, batch_id)


def get_batch_files(batch_id: str) -> List[Dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute("SELECT * FROM batch_files WHERE batch_id = %s ORDER BY file_index", (batch_id,)).fetchall()
    return _rows(rows)


def get_batch_job(batch_id: str) -> Optional[Dict[str, Any]]:
    with connection() as conn:
        row = conn.execute("SELECT * FROM batch_jobs WHERE batch_id = %s", (batch_id,)).fetchone()
    if not row:
        return None
    item = _row(row)
    item["file_statuses"] = _as_list(item.get("file_statuses"))
    return item


# ----------------------------------------------------------------------------
# Dashboard metrics
# ----------------------------------------------------------------------------
def get_dashboard_metrics(job_id: Optional[str] = None, source: Optional[str] = None) -> Dict[str, Any]:
    src = source.upper() if source and source.upper() in ("UPLOADED", "MOCK") else None
    with connection() as conn:
        counts = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE source = 'UPLOADED') AS uploaded,
                   COUNT(*) FILTER (WHERE source = 'MOCK') AS mock
            FROM candidates
            """
        ).fetchone()
        job_counts = conn.execute(
            "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE status = 'ACTIVE') AS active FROM jobs"
        ).fetchone()

        conditions, params = [], []
        if src:
            conditions.append("c.source = %s")
            params.append(src)
        if job_id:
            conditions.append("m.job_id = %s")
            params.append(job_id)
        query = "SELECT m.score, m.recommendation, m.candidate_id FROM match_results m JOIN candidates c ON m.candidate_id = c.candidate_id"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        match_rows = conn.execute(query, params).fetchall()

        def distinct_action(action: str) -> int:
            if src:
                return conn.execute(
                    "SELECT COUNT(DISTINCT r.candidate_id) AS n FROM recruiter_actions r "
                    "JOIN candidates c ON r.candidate_id = c.candidate_id WHERE r.action = %s AND c.source = %s",
                    (action, src),
                ).fetchone()["n"]
            return conn.execute(
                "SELECT COUNT(DISTINCT candidate_id) AS n FROM recruiter_actions WHERE action = %s", (action,)
            ).fetchone()["n"]

        shortlisted = distinct_action("SHORTLIST")
        rejected = distinct_action("REJECT")
        interview_count = distinct_action("INTERVIEW")

    total_all, uploaded_count, mock_count = counts["total"], counts["uploaded"], counts["mock"]
    if source and source.upper() == "UPLOADED":
        total_candidates = uploaded_count
    elif source and source.upper() == "MOCK":
        total_candidates = mock_count
    else:
        total_candidates = total_all

    strong_matches = sum(1 for r in match_rows if r["score"] >= 85 and r["recommendation"] == "STRONG MATCH")
    matches = sum(1 for r in match_rows if 70 <= r["score"] < 85)
    needs_review = sum(1 for r in match_rows if 50 <= r["score"] < 70)
    not_matched = sum(1 for r in match_rows if r["score"] < 50)

    score_dist = {"90-100": 0, "80-89": 0, "70-79": 0, "60-69": 0, "50-59": 0, "below-50": 0}
    for r in match_rows:
        s = r["score"]
        if s >= 90:
            score_dist["90-100"] += 1
        elif s >= 80:
            score_dist["80-89"] += 1
        elif s >= 70:
            score_dist["70-79"] += 1
        elif s >= 60:
            score_dist["60-69"] += 1
        elif s >= 50:
            score_dist["50-59"] += 1
        else:
            score_dist["below-50"] += 1

    scored_above = sum(score_dist[k] for k in ["90-100", "80-89", "70-79", "60-69", "50-59"])
    if total_candidates > scored_above:
        score_dist["below-50"] = max(score_dist["below-50"], total_candidates - scored_above)

    return {
        "total_candidates": total_candidates,
        "uploaded_candidates": uploaded_count,
        "mock_candidates": mock_count,
        "total_jobs": job_counts["total"],
        "active_jobs": job_counts["active"],
        "total_screened": len(match_rows),
        "strong_matches": strong_matches,
        "matches": matches,
        "needs_review": needs_review,
        "not_matched": not_matched,
        "shortlisted": shortlisted,
        "rejected": rejected,
        "interview_recommended": interview_count,
        "score_distribution": score_dist,
        "source_filter": source.upper() if source else "ALL",
    }


# ----------------------------------------------------------------------------
# Match results
# ----------------------------------------------------------------------------
def count_match_results() -> int:
    with connection() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM match_results").fetchone()["n"]


_UPSERT_MATCH = """
    INSERT INTO match_results (candidate_id, job_id, score, recommendation, matched_skills, missing_skills, reasoning, score_breakdown)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (candidate_id, job_id) DO UPDATE SET
        score = EXCLUDED.score, recommendation = EXCLUDED.recommendation,
        matched_skills = EXCLUDED.matched_skills, missing_skills = EXCLUDED.missing_skills,
        reasoning = EXCLUDED.reasoning, score_breakdown = EXCLUDED.score_breakdown, created_at = now()
"""


def _match_params(candidate_id: str, job_id: str, res: Dict[str, Any]) -> tuple:
    return (
        candidate_id,
        job_id,
        res["score"],
        res["recommendation"],
        _json(res.get("matched_skills", [])),
        _json(res.get("missing_skills", [])),
        strip_nul(res.get("reasoning")),
        _json(res.get("score_breakdown", {})),
    )


def upsert_match_result(candidate_id: str, job_id: str, res: Dict[str, Any]) -> None:
    with connection() as conn:
        conn.execute(_UPSERT_MATCH, _match_params(candidate_id, job_id, res))


def upsert_match_results(rows: List[tuple]) -> None:
    """rows: [(candidate_id, job_id, score_result), ...] in one transaction."""
    if not rows:
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(_UPSERT_MATCH, [_match_params(c, j, r) for c, j, r in rows])


def get_match_result(candidate_id: str, job_id: str) -> Optional[Dict[str, Any]]:
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM match_results WHERE candidate_id = %s AND job_id = %s", (candidate_id, job_id)
        ).fetchone()
    return _row(row)


def get_ranked_candidates_for_job(job_id: str) -> List[Dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT m.*, c.full_name, c.location, c.roles, c.skills, c.years_experience, c.source, c.status AS cand_status
            FROM match_results m
            JOIN candidates c ON m.candidate_id = c.candidate_id
            WHERE m.job_id = %s
            ORDER BY m.score DESC, m.candidate_id
            """,
            (job_id,),
        ).fetchall()
    return _rows(rows)
