"""Batch CV upload: files staged in CV storage, progress in PostgreSQL
(batch_jobs + batch_files), one SQS message per file for the worker.

BATCH_BACKEND=sqs   the API enqueues; `python -m backend.app.worker` processes.
BATCH_BACKEND=inline the API process works through the batch itself (local
                    development and tests), using the same process_file().
"""
import asyncio
import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from backend.app.config import settings
from backend.app.db import database as db
from backend.app.services import cv_pipeline
from backend.app.services.cv_storage import batch_key, content_type_for, get_cv_storage

logger = logging.getLogger(__name__)

DONE = "done"
RETRY = "retry"

_sqs_client = None
_inline_tasks: set = set()


def sqs_client():
    global _sqs_client
    if _sqs_client is None:
        import boto3
        from botocore.config import Config

        _sqs_client = boto3.client(
            "sqs",
            region_name=settings.AWS_REGION,
            config=Config(retries={"max_attempts": 5, "mode": "standard"}, connect_timeout=5, read_timeout=30),
        )
    return _sqs_client


def set_sqs_client(client) -> None:
    global _sqs_client
    _sqs_client = client


def new_candidate_id() -> str:
    return f"CAND-{str(uuid.uuid4())[:8].upper()}"


# --------------------------------------------------------------------------- API side
async def start_batch(files: List[Tuple[Optional[str], bytes]], job_id: Optional[str] = None) -> Dict[str, Any]:
    """Stage the files, record the batch and queue one message per file.
    Files over the size limit are left out, as before."""
    batch_id = f"BATCH-{uuid.uuid4().hex[:8].upper()}"
    storage = get_cv_storage()
    rows: List[Dict[str, Any]] = []
    for filename, content in files:
        if len(content) > cv_pipeline.MAX_FILE_SIZE:
            continue
        index = len(rows)
        ext = cv_pipeline.file_extension(filename) or "txt"
        key = batch_key(batch_id, index, ext)
        await asyncio.to_thread(storage.put, key, content, content_type_for(ext), None)
        rows.append({
            "file_index": index,
            "filename": filename or f"file-{index}",
            "file_type": ext,
            "staging_key": key,
            "size_bytes": len(content),
        })

    await asyncio.to_thread(db.create_batch, batch_id, job_id, rows)

    if rows:
        if settings.BATCH_BACKEND == "sqs":
            await asyncio.to_thread(_enqueue, batch_id, [r["file_index"] for r in rows])
        else:
            task = asyncio.create_task(process_batch_inline(batch_id, [r["file_index"] for r in rows]))
            _inline_tasks.add(task)
            task.add_done_callback(_inline_tasks.discard)

    return {"batch_id": batch_id, "total": len(rows), "status": "PROCESSING"}


def _enqueue(batch_id: str, indexes: List[int]) -> None:
    client = sqs_client()
    for start in range(0, len(indexes), 10):
        chunk = indexes[start:start + 10]
        try:
            resp = client.send_message_batch(
                QueueUrl=settings.BATCH_QUEUE_URL,
                Entries=[
                    {"Id": str(i), "MessageBody": json.dumps({"batch_id": batch_id, "file_index": i})}
                    for i in chunk
                ],
            )
            failed = [int(f["Id"]) for f in resp.get("Failed", [])]
        except Exception as err:
            logger.error("Could not queue batch %s files %s: %s", batch_id, chunk, err)
            failed = chunk
        for i in failed:
            db.finish_batch_file(batch_id, i, "FAILED", error="Could not queue the file for processing")


async def process_batch_inline(batch_id: str, indexes: List[int]) -> None:
    for index in indexes:
        for _ in range(settings.WORKER_MAX_ATTEMPTS):
            if await process_file(batch_id, index) == DONE:
                break


def batch_status(batch_id: str) -> Optional[Dict[str, Any]]:
    """Same shape as the former in-memory progress object."""
    job = db.get_batch_job(batch_id)
    if not job:
        return None
    status = {
        "batch_id": batch_id,
        "total": job["total"],
        "completed": job["completed"],
        "processing": job["processing"],
        "queued": job["queued"],
        "failed": job["failed"],
        "files": [
            {
                "filename": f.get("filename"),
                "status": f.get("status"),
                "candidate_id": f.get("candidate_id"),
                "error": f.get("error"),
            }
            for f in job["file_statuses"]
        ],
    }
    if job.get("status") == "COMPLETE":
        status["status"] = "COMPLETE"
    return status


# --------------------------------------------------------------------------- worker side
class PermanentError(Exception):
    """The file can never succeed (bad format, unreadable text)."""


async def process_file(batch_id: str, file_index: int) -> str:
    """Process one batch file. Returns DONE when the file reached a final state
    (the message can be deleted) or RETRY when it should be tried again."""
    claimed = await asyncio.to_thread(db.claim_batch_file, batch_id, file_index, new_candidate_id())
    if not claimed:
        return DONE  # already final, or unknown: a duplicate delivery

    candidate_id = claimed["candidate_id"]
    filename = claimed["filename"]
    ext = claimed["file_type"]
    storage = get_cv_storage()
    try:
        if ext not in cv_pipeline.SUPPORTED_EXTENSIONS:
            raise PermanentError(f"Unsupported format: {ext}")

        content = await asyncio.to_thread(storage.get, claimed["staging_key"])
        sha256_hash = db.calculate_sha256(content)
        dup = await asyncio.to_thread(db.check_duplicate_file, sha256_hash)
        if dup and dup["candidate_id"] != candidate_id:
            await asyncio.to_thread(db.finish_batch_file, batch_id, file_index, "SKIPPED", "Duplicate file", None)
            await _drop_staging(claimed)
            return DONE

        try:
            cv_text = cv_pipeline.extract_text(ext, content)
        except Exception as err:
            raise PermanentError(str(err)) from err

        if not dup:  # on a retry the original may already be stored
            await cv_pipeline.store_original(candidate_id, filename, ext, sha256_hash, content)
        await cv_pipeline.extract_and_save(cv_text, candidate_id, filename, sha256_hash)

        await asyncio.to_thread(db.finish_batch_file, batch_id, file_index, "COMPLETED", None, candidate_id)
        await _drop_staging(claimed)
        return DONE

    except PermanentError as err:
        logger.warning("Batch %s file %s failed: %s", batch_id, file_index, err)
        await asyncio.to_thread(db.finish_batch_file, batch_id, file_index, "FAILED", str(err), None)
        await _drop_staging(claimed)
        return DONE
    except Exception as err:
        attempts = claimed.get("attempts", 1)
        logger.error("Batch %s file %s attempt %s failed: %s", batch_id, file_index, attempts, err)
        if attempts >= settings.WORKER_MAX_ATTEMPTS:
            await asyncio.to_thread(db.finish_batch_file, batch_id, file_index, "FAILED", str(err), None)
            return DONE
        await asyncio.to_thread(db.requeue_batch_file, batch_id, file_index, str(err))
        return RETRY


async def _drop_staging(file_row: Dict[str, Any]) -> None:
    key = file_row.get("staging_key")
    if not key:
        return
    try:
        await asyncio.to_thread(get_cv_storage().delete, key)
    except Exception as err:  # the bucket lifecycle rule removes leftovers
        logger.info("Staged batch file %s not deleted: %s", key, err)
