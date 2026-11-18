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
    # 3. once the worker has finished, the evidence report (changes nothing):
    python -m backend.app.dataload.import_cvs --prefix import/2026-11-17/ \
        --report s3://<cv bucket>/migration/reports/

The report (the post-migration changes report) first lists any cleanup runs
recorded by remove_source (e.g. the MOCK demo candidates removed) and any
re-extraction runs recorded by reextract (AI extraction redone), then
accounts for every file under the prefix: its SHA-256, the
candidate it became, the stored copy's S3 checksum (must equal the source),
and whether the AI extraction found a name. Result PASS when every supported
file is IMPORTED (or a DUPLICATE of another file in the set) with a matching
checksum; anything else is listed and the result is FAIL (exit code 1).

Each file is copied to the batch staging area (batch/...), so the files under
the import prefix stay untouched until you delete them. Files are grouped into
batches of --batch-size (default 250); progress shows in the app like any
batch upload (GET /api/batch-status/{batch_id}) and in the batch_jobs table.
A file whose content is already in the portal (same SHA-256) is SKIPPED by the
worker, so running the import twice does not create duplicates.
"""
import argparse
import hashlib
import json
import logging
import os
import posixpath
import sys
import tempfile
from datetime import datetime, timezone
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


# --------------------------------------------------------------------------- evidence report
def _raw(cand: Dict[str, Any]) -> Dict[str, Any]:
    raw = cand.get("raw_json")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    return raw if isinstance(raw, dict) else {}


def build_report(prefix: str) -> Dict[str, Any]:
    """Account for every file under the prefix after the worker has run."""
    storage = get_cv_storage()
    p = plan(storage.list_keys(prefix))
    files: List[Dict[str, Any]] = []
    first_by_sha: Dict[str, str] = {}
    for f in p["files"]:
        content = storage.get(f["key"])
        sha = hashlib.sha256(content).hexdigest()
        entry: Dict[str, Any] = {"file": f["key"][len(prefix):], "sha256": sha, "size_bytes": len(content)}
        if len(content) > cv_pipeline.MAX_FILE_SIZE:
            entry["status"] = "TOO_LARGE"
        elif sha in first_by_sha:
            entry["status"] = "DUPLICATE"
            entry["duplicate_of"] = first_by_sha[sha]
        else:
            first_by_sha[sha] = entry["file"]
            stored = db.check_duplicate_file(sha)
            if not stored:
                entry["status"] = "NOT_IMPORTED"
            else:
                cand = db.get_candidate_row(stored["candidate_id"]) or {}
                stored_sha = storage.checksum_sha256(stored["s3_key"]) if stored.get("s3_key") else None
                entry.update({
                    "candidate_id": stored["candidate_id"],
                    "s3_key": stored.get("s3_key"),
                    "stored_sha256": stored_sha,
                    "name_extracted": bool((cand.get("full_name") or "").strip()),
                    "llm_fallback": bool(_raw(cand).get("llm_fallback")),
                    "candidate_status": cand.get("status"),
                })
                entry["status"] = "IMPORTED" if stored_sha == sha else "CHECKSUM_MISMATCH"
        files.append(entry)

    counts: Dict[str, int] = {}
    for e in files:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    problems = [e for e in files if e["status"] not in ("IMPORTED", "DUPLICATE")]
    imported = [e for e in files if e["status"] == "IMPORTED"]
    from backend.app.dataload.reextract import reextract_records
    from backend.app.dataload.remove_source import cleanup_records

    removals = cleanup_records()
    reextractions = reextract_records()
    with db.connection() as conn:
        inventory = {r["s"]: r["n"] for r in conn.execute(
            "SELECT COALESCE(source, 'None') AS s, COUNT(*) AS n FROM candidates GROUP BY 1 ORDER BY 1").fetchall()}
    return {
        "report": "RAASHiring post-migration changes",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "prefix": prefix,
        "result": "PASS" if files and not problems and all(r.get("result") == "PASS" for r in removals) else "FAIL",
        "removals": removals,
        "reextractions": reextractions,
        "candidates_by_source_now": inventory,
        "totals": {
            "files_found": len(files) + len(p["skipped"]),
            "supported_files": len(files),
            "skipped_unsupported": len(p["skipped"]),
            "by_status": counts,
            "imported_without_extracted_name": sum(1 for e in imported if not e.get("name_extracted")),
            "imported_from_heuristic_fallback": sum(1 for e in imported if e.get("llm_fallback")),
        },
        "problems": problems,
        "skipped": p["skipped"],
        "files": files,
    }


def write_report(report: Dict[str, Any], destination: Optional[str]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    body = json.dumps(report, indent=2, default=str, ensure_ascii=False)
    if destination and destination.startswith("s3://"):
        import boto3

        bucket, _, key_prefix = destination[5:].partition("/")
        key = (key_prefix.rstrip("/") + "/" if key_prefix else "") + f"import-report-{stamp}.json"
        boto3.client("s3", region_name=settings.AWS_REGION).put_object(
            Bucket=bucket, Key=key, Body=body.encode(), ContentType="application/json", ServerSideEncryption="aws:kms"
        )
        return f"s3://{bucket}/{key}"
    path = destination or os.path.join(tempfile.gettempdir(), f"import-report-{stamp}.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return path


def print_summary(report: Dict[str, Any], where: str) -> None:
    t = report["totals"]
    lines = ["", "=" * 70, f"RAASHiring post-migration changes: {report['result']}", "=" * 70]
    for r in report.get("removals", []):
        lines.append(f"Removed:             {r.get('removed_candidates')} {r.get('source')} candidates "
                     f"on {r.get('run_at')} ({r.get('result')}): {r.get('reason')}")
    for r in report.get("reextractions", []):
        t_r = r.get("totals", {})
        lines.append(f"Re-extracted:        {t_r.get('by_status', {}).get('REEXTRACTED', 0)} of {t_r.get('listed')} "
                     f"candidates on {r.get('finished_at')} ({r.get('result')}): {r.get('reason')}")
    lines += [f"Import prefix:       {report['prefix']}",
             f"Files found:         {t['files_found']}",
             f"Unsupported/hidden:  {t['skipped_unsupported']}"]
    for status, n in sorted(t["by_status"].items()):
        lines.append(f"{status + ':':<21}{n}")
    lines.append(f"Imported, no name:   {t['imported_without_extracted_name']}  (check these candidates in the portal)")
    lines.append(f"Heuristic fallback:  {t['imported_from_heuristic_fallback']}  (redo with dataload.reextract --fallbacks)")
    for e in report["problems"][:20]:
        lines.append(f"  {e['status']}: {e['file']}")
    if len(report["problems"]) > 20:
        lines.append(f"  ... and {len(report['problems']) - 20} more in the report")
    lines.append("Candidates now:      " + ", ".join(f"{k} {v}" for k, v in report.get("candidates_by_source_now", {}).items()))
    lines += [f"Report: {where}", "=" * 70]
    print("\n".join(lines))


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prefix", required=True, help="key prefix in the CV bucket, e.g. import/2026-11-17/")
    ap.add_argument("--job-id", help="optional job to attach the batches to")
    ap.add_argument("--batch-size", type=int, default=250)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", metavar="DEST",
                    help="write the evidence report instead of importing: s3://bucket/prefix/ or a local path")
    args = ap.parse_args(argv)

    if args.report:
        report = build_report(args.prefix)
        print_summary(report, write_report(report, args.report))
        return 0 if report["result"] == "PASS" else 1

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
