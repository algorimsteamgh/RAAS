"""Post-migration cleanup: remove every candidate of one source (e.g. the MOCK
demo candidates) with their CV files, matches, recruiter actions and chat, at
the customer's request. Run it after the migration has been validated, as a
one-off ECS task (migrate task definition):

    python -m backend.app.dataload.remove_source --source MOCK \\
        --reason "Demo data removed at Quess Global's request (17 Nov 2026)" [--dry-run]

Everything happens in one transaction, and the run is recorded in the
database itself: one audit_logs row per removed candidate (event
DATA_CLEANUP) and one summary row (DATA_CLEANUP_SUMMARY, JSON details). The
import report (import_cvs --report) reads these rows into the post-migration
changes report. Audit history of the removed candidates is kept.

Checks, printed as PASS/FAIL (exit code 1 on FAIL):
  * no candidate of that source is left;
  * every other candidate is unchanged (same ids and same row content);
  * jobs are unchanged.
"""
import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.db import database as db

logger = logging.getLogger("remove_source")

COUNTED = ["candidates", "original_files", "match_results", "recruiter_actions", "candidate_chat_messages", "jobs", "audit_logs"]


def _counts(conn) -> Dict[str, int]:
    return {t: conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"] for t in COUNTED}


def _by_source(conn) -> Dict[str, int]:
    rows = conn.execute("SELECT COALESCE(source, 'None') AS s, COUNT(*) AS n FROM candidates GROUP BY 1 ORDER BY 1").fetchall()
    return {r["s"]: r["n"] for r in rows}


def _fingerprint(conn, sql: str, params=()) -> str:
    """One hash over the rows a query returns, to show they did not change."""
    h = hashlib.sha256()
    for r in conn.execute(sql, params).fetchall():
        h.update(json.dumps(r, sort_keys=True, default=str).encode())
    return h.hexdigest()


def remove_source(source: str, reason: str, dry_run: bool = False) -> Dict[str, Any]:
    source = source.strip()
    if not source or source.upper() == "UPLOADED":
        raise ValueError("Refusing to remove real (UPLOADED) candidates; name a demo source such as MOCK")
    if not reason.strip():
        raise ValueError("--reason is required: it is recorded in the audit log and the report")

    others_sql = "SELECT * FROM candidates WHERE UPPER(COALESCE(source, '')) <> UPPER(%s) ORDER BY candidate_id"
    jobs_sql = "SELECT * FROM jobs ORDER BY job_id"
    when = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db.connection() as conn:
        ids = [r["candidate_id"] for r in conn.execute(
            "SELECT candidate_id FROM candidates WHERE UPPER(COALESCE(source, '')) = UPPER(%s) ORDER BY candidate_id",
            (source,)).fetchall()]
        before = {"counts": _counts(conn), "candidates_by_source": _by_source(conn)}
        others_before = _fingerprint(conn, others_sql, (source,))
        jobs_before = _fingerprint(conn, jobs_sql)
        keys = db._cv_keys_for(conn, ids)
        summary: Dict[str, Any] = {
            "job": "remove_source",
            "source": source.upper(),
            "reason": reason,
            "run_at": when,
            "dry_run": dry_run,
            "candidates_to_remove": len(ids),
            "cv_files_to_remove": len(keys),
            "before": before,
        }
        if dry_run:
            summary["candidate_ids"] = ids
            conn.rollback()
            return summary

        for cid in ids:
            db._delete_candidate_rows(conn, cid)
            db.log_audit_event("DATA_CLEANUP", cid, f"{source.upper()} candidate removed: {reason}", conn=conn)

        after = {"counts": _counts(conn), "candidates_by_source": _by_source(conn)}
        checks = {
            "no_candidates_of_source_left": not conn.execute(
                "SELECT 1 FROM candidates WHERE UPPER(COALESCE(source, '')) = UPPER(%s) LIMIT 1", (source,)).fetchone(),
            "other_candidates_unchanged": _fingerprint(conn, others_sql, (source,)) == others_before,
            "jobs_unchanged": _fingerprint(conn, jobs_sql) == jobs_before,
        }
        summary.update({
            "removed_candidates": len(ids),
            "removed_cv_files": len(keys),
            "after": after,
            "checks": checks,
            "result": "PASS" if all(checks.values()) else "FAIL",
            "candidate_ids": ids,
        })
        if summary["result"] != "PASS":
            raise RuntimeError(f"Cleanup checks failed, nothing was removed: {checks}")
        db.log_audit_event("DATA_CLEANUP_SUMMARY", None,
                           json.dumps({k: v for k, v in summary.items() if k != "candidate_ids"}), conn=conn)
    db._delete_cv_objects(keys)  # after the commit, as the app's own delete does
    return summary


def cleanup_records() -> List[Dict[str, Any]]:
    """The cleanup runs recorded in the database, with the removed ids."""
    with db.connection() as conn:
        runs = conn.execute(
            "SELECT id, details, \"timestamp\" FROM audit_logs WHERE event_type = 'DATA_CLEANUP_SUMMARY' ORDER BY id"
        ).fetchall()
        out = []
        prev_id = 0
        for r in runs:
            try:
                details = json.loads(r["details"])
            except (TypeError, ValueError):
                details = {"details": r["details"]}
            ids = [x["candidate_id"] for x in conn.execute(
                "SELECT candidate_id FROM audit_logs WHERE event_type = 'DATA_CLEANUP' AND id > %s AND id < %s "
                "AND details = %s ORDER BY candidate_id",
                (prev_id, r["id"], f"{details.get('source', '')} candidate removed: {details.get('reason', '')}"),
            ).fetchall()]
            details["candidate_ids"] = ids
            prev_id = r["id"]
            out.append(details)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, help="candidate source to remove, e.g. MOCK")
    ap.add_argument("--reason", required=True, help="recorded in the audit log and the changes report")
    ap.add_argument("--dry-run", action="store_true", help="show what would be removed; change nothing")
    args = ap.parse_args(argv)
    summary = remove_source(args.source, args.reason, args.dry_run)
    shown = {k: v for k, v in summary.items() if k != "candidate_ids"}
    print(json.dumps(shown, indent=2, default=str))
    return 0 if args.dry_run or summary.get("result") == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
