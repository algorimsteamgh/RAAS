"""Redo the AI extraction for candidates whose profile came from the layout
heuristic parser because the Bedrock call failed (for example throttling
during the 17 Nov 2026 bulk import). The stored CV is read again and sent to
Bedrock; the candidate row is replaced only with a real AI extraction, never
with another heuristic result. Ids, CV files, the upload time and everything
else about the candidate stay as they are.

Run it as a one-off ECS task with the api task definition:

    python -m backend.app.dataload.reextract --ids s3://<cv bucket>/migration/reextract/ids.txt \\
        [--rpm 6] [--dry-run] [--report s3://<cv bucket>/migration/reports/]
    python -m backend.app.dataload.reextract --fallbacks [...]

--ids is a text file (s3:// or local) with one candidate id per line.
--fallbacks takes every candidate marked llm_fallback (marked since
18 Nov 2026; earlier fallbacks are found from the worker log).

--rpm caps this task's Bedrock calls per minute: keep it under the account's
quota minus what the portal needs (quota 10: use 6). A throttled call waits
and is tried again (--max-tries); a candidate that still fails is left
unchanged and listed. The run is recorded in audit_logs (REEXTRACT per
candidate, REEXTRACT_SUMMARY per run) and read into the post-migration
changes report (import_cvs --report).

Result PASS (exit 0) when every listed candidate was re-extracted.
"""
import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from backend.app.config import settings
from backend.app.db import database as db
from backend.app.services import cv_pipeline
from backend.app.services.cv_storage import get_cv_storage

logger = logging.getLogger("reextract")

FALLBACK_SQL = (
    "SELECT candidate_id FROM candidates WHERE raw_json->>'llm_fallback' = 'true' "
    "ORDER BY candidate_id"
)
RETRYABLE = {"ThrottlingException", "ServiceUnavailableException", "ModelNotReadyException",
             "InternalServerException", "ReadTimeoutError", "ConnectTimeoutError"}


def _error_code(err: Exception) -> str:
    response = getattr(err, "response", None) or {}
    return response.get("Error", {}).get("Code", "") or type(err).__name__


def read_ids(source: str) -> List[str]:
    if source.startswith("s3://"):
        import boto3

        bucket, _, key = source[5:].partition("/")
        body = boto3.client("s3", region_name=settings.AWS_REGION).get_object(Bucket=bucket, Key=key)["Body"].read()
        text = body.decode("utf-8")
    else:
        with open(source, encoding="utf-8") as fh:
            text = fh.read()
    seen: Dict[str, None] = {}
    for line in text.splitlines():
        cid = line.strip()
        if cid and not cid.startswith("#"):
            seen.setdefault(cid, None)
    return list(seen)


def fallback_ids() -> List[str]:
    with db.connection() as conn:
        return [r["candidate_id"] for r in conn.execute(FALLBACK_SQL).fetchall()]


def _raw(row: Dict[str, Any]) -> Dict[str, Any]:
    raw = row.get("raw_json")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    return raw if isinstance(raw, dict) else {}


def make_agent(rpm: float):
    from backend.app.agents.cv_agent import CVExtractionAgent
    from backend.app.services.llm import get_llm_client

    client = get_llm_client()
    if getattr(client, "backend", "") == "bedrock":
        from backend.app.services.llm.bedrock_client import BedrockClient

        client = BedrockClient(max_rpm=rpm)
    return CVExtractionAgent(llm_client=client, allow_fallback=False)


async def reextract_one(agent: Any, candidate_id: str, storage: Any, max_tries: int, dry_run: bool,
                        sleep: Callable[[float], Any] = asyncio.sleep) -> Dict[str, Any]:
    entry: Dict[str, Any] = {"candidate_id": candidate_id}
    row = db.get_candidate_row(candidate_id)
    if not row:
        entry["status"] = "NOT_FOUND"
        return entry
    entry["llm_fallback_before"] = _raw(row).get("llm_fallback")
    if (row.get("source") or "").upper() != "UPLOADED":
        entry["status"] = "SKIPPED_NOT_UPLOADED"
        return entry
    original = db.get_original_file(candidate_id)
    if not original or not original.get("s3_key"):
        entry["status"] = "NO_CV_FILE"
        return entry
    content = storage.get(original["s3_key"])
    sha = hashlib.sha256(content).hexdigest()
    if original.get("sha256_hash") and sha != original["sha256_hash"]:
        entry["status"] = "CHECKSUM_MISMATCH"
        return entry
    if dry_run:
        entry["status"] = "WOULD_REEXTRACT"
        return entry
    ext = original.get("file_type") or cv_pipeline.file_extension(original.get("filename"))
    try:
        text = cv_pipeline.extract_text(ext, content)
    except Exception as err:  # unreadable file: nothing an LLM retry can fix
        entry.update(status="FAILED", error=f"text extraction: {type(err).__name__}")
        return entry

    delay = 30.0
    for attempt in range(1, max_tries + 1):
        try:
            candidate = await agent.extract_candidate(text, candidate_id=candidate_id)
            break
        except Exception as err:
            code = _error_code(err)
            entry["attempts"] = attempt
            if code not in RETRYABLE or attempt == max_tries:
                entry.update(status="FAILED", error=code)
                return entry
            logger.info("%s: %s, waiting %ds (attempt %d/%d)", candidate_id, code, delay, attempt, max_tries)
            await sleep(delay)
            delay = min(delay * 2, 300.0)
    cand = candidate.model_dump()
    db.save_candidate_record(cand, row.get("source") or "UPLOADED", "COMPLETED",
                             row.get("filename") or original.get("filename") or "",
                             row.get("file_hash") or original.get("sha256_hash") or "",
                             keep_created_at=True)
    entry.update(status="REEXTRACTED", extraction_method=cand.get("extraction_method"),
                 name_extracted=bool((cand.get("full_name") or "").strip()))
    return entry


async def run(ids: List[str], rpm: float, max_tries: int, dry_run: bool, reason: str,
              agent: Any = None, storage: Any = None,
              sleep: Callable[[float], Any] = asyncio.sleep) -> Dict[str, Any]:
    started = datetime.now(timezone.utc)
    agent = agent or (None if dry_run else make_agent(rpm))
    storage = storage or get_cv_storage()
    results: List[Dict[str, Any]] = []
    t0 = time.monotonic()
    for n, cid in enumerate(ids, 1):
        entry = await reextract_one(agent, cid, storage, max_tries, dry_run, sleep)
        results.append(entry)
        if not dry_run and entry["status"] in ("REEXTRACTED", "FAILED"):
            db.log_audit_event("REEXTRACT", cid, json.dumps(
                {"status": entry["status"], "llm_fallback_before": entry.get("llm_fallback_before"),
                 "extraction_method": entry.get("extraction_method"), "error": entry.get("error")}))
        if n % 25 == 0 or n == len(ids):
            elapsed = time.monotonic() - t0
            logger.info("Progress %d/%d (%.0f min elapsed, about %.0f min left)",
                        n, len(ids), elapsed / 60, elapsed / n * (len(ids) - n) / 60)

    counts: Dict[str, int] = {}
    for e in results:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    ok_status = "WOULD_REEXTRACT" if dry_run else "REEXTRACTED"
    problems = [e for e in results if e["status"] != ok_status]
    report = {
        "report": "RAASHiring AI re-extraction",
        "dry_run": dry_run,
        "reason": reason,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": settings.BEDROCK_MODEL_ID if settings.MODEL_BACKEND == "bedrock" else settings.MODEL_BACKEND,
        "max_rpm": rpm,
        "result": "PASS" if ids and not problems else "FAIL",
        "totals": {"listed": len(ids), "by_status": counts,
                   "reextracted_without_name": sum(1 for e in results if e["status"] == "REEXTRACTED"
                                                   and not e.get("name_extracted"))},
        "problems": problems,
        "candidates": results,
    }
    if not dry_run:
        summary = {k: report[k] for k in ("reason", "started_at", "finished_at", "model", "max_rpm", "result")}
        summary["totals"] = report["totals"]
        db.log_audit_event("REEXTRACT_SUMMARY", None, json.dumps(summary))
    return report


def reextract_records() -> List[Dict[str, Any]]:
    """The re-extraction runs recorded in the database (for the import report)."""
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT details FROM audit_logs WHERE event_type = 'REEXTRACT_SUMMARY' ORDER BY id").fetchall()
    out = []
    for r in rows:
        try:
            out.append(json.loads(r["details"]))
        except (TypeError, ValueError):
            out.append({"details": r["details"]})
    return out


def write_report(report: Dict[str, Any], destination: Optional[str]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    body = json.dumps(report, indent=2, default=str, ensure_ascii=False)
    name = f"reextract-report-{stamp}.json"
    if destination and destination.startswith("s3://"):
        import boto3

        bucket, _, key_prefix = destination[5:].partition("/")
        key = (key_prefix.rstrip("/") + "/" if key_prefix else "") + name
        boto3.client("s3", region_name=settings.AWS_REGION).put_object(
            Bucket=bucket, Key=key, Body=body.encode(), ContentType="application/json", ServerSideEncryption="aws:kms"
        )
        return f"s3://{bucket}/{key}"
    path = destination or os.path.join(tempfile.gettempdir(), name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return path


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--ids", help="file with one candidate id per line (s3://... or a local path)")
    src.add_argument("--fallbacks", action="store_true", help="every candidate marked llm_fallback")
    ap.add_argument("--rpm", type=float, default=6.0, help="Bedrock calls per minute at most (default 6)")
    ap.add_argument("--max-tries", type=int, default=8, help="tries per candidate on throttling (default 8)")
    ap.add_argument("--reason", default="AI extraction redone for profiles saved from the heuristic parser "
                                        "after Bedrock throttling during the bulk import")
    ap.add_argument("--dry-run", action="store_true", help="check every candidate and its CV file; change nothing")
    ap.add_argument("--report", metavar="DEST", help="where to write the JSON report: s3://bucket/prefix/ or a path")
    args = ap.parse_args(argv)

    ids = read_ids(args.ids) if args.ids else fallback_ids()
    logger.info("%d candidate(s) to re-extract at up to %.1f Bedrock calls a minute (about %.0f min)",
                len(ids), args.rpm, len(ids) / max(args.rpm, 0.1))
    report = asyncio.run(run(ids, args.rpm, args.max_tries, args.dry_run, args.reason))
    where = write_report(report, args.report)
    print(json.dumps({k: report[k] for k in ("result", "dry_run", "totals")}, indent=2))
    for e in report["problems"][:20]:
        print(f"  {e['candidate_id']}: {e['status']} {e.get('error', '')}")
    print(f"Report: {where}")
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
