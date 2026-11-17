"""Bulk import of CV files that were uploaded to the CV bucket, through the
normal batch pipeline (text extraction, Bedrock extraction, candidate rows),
processed by the worker service. For large sets (e.g. the 2,000 real resumes
that replace the demo candidates) instead of uploading through the browser.

    # 1. upload the files (PDF, DOCX, TXT, PNG, JPG; up to 10 MB each):
    aws s3 sync ./resumes s3://<cv bucket>/import/2026-11-17/   (bucket default: SSE-KMS)
    # 2. run this as a one-off ECS task with the api task definition
    #    (its role may read the bucket and send to the batch queue):
    python -m backend.app.dataload.import_cvs --prefix import/2026-11-17/ [--job-id JOB-ID]
    # --dry-run lists what would be imported without changing anything.

Each file is copied to the batch staging area (batch/...), so the files under
the import prefix stay untouched until you delete them. Files are grouped into
batches of --batch-size (default 250); progress shows in the app like any
batch upload (GET /api/batch-status/{batch_id}) and in the batch_jobs table.
A file whose content is already in the portal (same SHA-256) is SKIPPED by the
worker, so running the import twice does not create duplicates.
"""
import argparse
import json
import logging
import posixpath
import sys
from typing import Any, Dict, List, Optional

from backend.app.config import settings
from backend.app.db import database as db
from backend.app.services import batch_service, cv_pipeline
from backend.app.services.cv_storage import batch_key, content_type_for, get_cv_storage

logger = logging.getLogger("import_cvs")


def plan(keys: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """Split the listed keys into importable files and skipped ones."""
    files: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for key in sorted(keys):
        if key.endswith("/"):
            continue
        name = posixpath.basename(key)
        if name.startswith("."):
            skipped.append({"key": key, "reason": "hidden file"})
            continue
        ext = cv_pipeline.file_extension(name)
        if ext not in cv_pipeline.SUPPORTED_EXTENSIONS:
            skipped.append({"key": key, "reason": f"unsupported format: {ext or 'none'}"})
            continue
        files.append({"key": key, "filename": name, "file_type": ext})
    return {"files": files, "skipped": skipped}


def import_prefix(prefix: str, job_id: Optional[str] = None, batch_size: int = 250,
                  dry_run: bool = False) -> Dict[str, Any]:
    if not prefix or prefix.startswith(("cvs/", "batch/", "migration/")):
        raise ValueError("Use a dedicated prefix such as import/2026-11-17/")
    storage = get_cv_storage()
    p = plan(storage.list_keys(prefix))
    summary: Dict[str, Any] = {
        "prefix": prefix,
        "found": len(p["files"]) + len(p["skipped"]),
        "to_import": len(p["files"]),
        "skipped": p["skipped"],
        "batches": [],
    }
    if dry_run or not p["files"]:
        return summary

    use_sqs = settings.BATCH_BACKEND == "sqs"
    for start in range(0, len(p["files"]), batch_size):
        chunk = p["files"][start:start + batch_size]
        batch_id = f"BATCH-IMP-{batch_service.new_candidate_id()[5:]}"
        rows: List[Dict[str, Any]] = []
        for f in chunk:
            index = len(rows)
            content = storage.get(f["key"])
            if len(content) > cv_pipeline.MAX_FILE_SIZE:
                summary["skipped"].append({"key": f["key"], "reason": "larger than 10 MB"})
                continue
            key = batch_key(batch_id, index, f["file_type"])
            storage.put(key, content, content_type_for(f["file_type"]), None)
            rows.append({
                "file_index": index,
                "filename": f["filename"],
                "file_type": f["file_type"],
                "staging_key": key,
                "size_bytes": len(content),
            })
        if not rows:
            continue
        db.create_batch(batch_id, job_id, rows)
        if use_sqs:
            batch_service._enqueue(batch_id, [r["file_index"] for r in rows])
        summary["batches"].append({"batch_id": batch_id, "files": len(rows)})
        logger.info("Queued %s with %d files (%d/%d)", batch_id, len(rows),
                    min(start + batch_size, len(p["files"])), len(p["files"]))
    summary["queued"] = sum(b["files"] for b in summary["batches"])
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prefix", required=True, help="key prefix in the CV bucket, e.g. import/2026-11-17/")
    ap.add_argument("--job-id", help="optional job to attach the batches to")
    ap.add_argument("--batch-size", type=int, default=250)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if settings.STORAGE_BACKEND != "s3" and not args.dry_run:
        logger.warning("STORAGE_BACKEND is %s, not s3", settings.STORAGE_BACKEND)
    if settings.BATCH_BACKEND != "sqs" and not args.dry_run:
        logger.error("BATCH_QUEUE_URL is not set: nothing would process the files. Run it in the api task.")
        return 2

    summary = import_prefix(args.prefix, args.job_id, max(1, min(args.batch_size, 1000)), args.dry_run)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
