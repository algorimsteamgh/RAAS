"""Post-load verification (RAAS-MIG-05 section 5). Every check records PASS or
FAIL in the report; the source side is the converted SQLite data after the
seed-data rule, the target side is read back from PostgreSQL and S3."""
import hashlib
import logging
import sqlite3
from typing import Any, Dict, List, Set

from backend.app.dataload.tables import TABLES, TABLES_BY_NAME, Table, canonical, pk_of, row_hash
from backend.app.db import database as db
from backend.app.services.cv_storage import cv_key, get_cv_storage

logger = logging.getLogger("raas.dataload.verify")

MAX_LISTED = 50


def _status(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _target_rows(conn, table: Table) -> List[Dict[str, Any]]:
    cols = ", ".join(f'"{c}"' for c in table.column_names)
    return conn.execute(f'SELECT {cols} FROM "{table.name}"').fetchall()


def verify_tables(conn, data: Dict[str, List[Dict[str, Any]]], excluded_counts: Dict[str, int]) -> Dict[str, Any]:
    results = {}
    for table in TABLES:
        source = {pk_of(table, r): row_hash(table, r) for r in data[table.name]}
        target = {pk_of(table, r): row_hash(table, r) for r in _target_rows(conn, table)}
        matched = sum(1 for k, h in source.items() if target.get(k) == h)
        mismatched = [k for k, h in source.items() if k in target and target[k] != h]
        missing = [k for k in source if k not in target]
        extra = [k for k in target if k not in source]
        ok = len(source) == len(target) == matched
        results[table.name] = {
            "source_count": len(source),
            "excluded": excluded_counts.get(table.name, 0),
            "target_count": len(target),
            "hash_matched": matched,
            "hash_mismatched": mismatched[:MAX_LISTED],
            "missing_in_target": missing[:MAX_LISTED],
            "extra_in_target": extra[:MAX_LISTED],
            "status": _status(ok),
        }
    return results


def verify_cv_files(conn, sconn: sqlite3.Connection, deep: bool) -> Dict[str, Any]:
    storage = get_cv_storage()
    rows = conn.execute("SELECT candidate_id, file_type, sha256_hash, s3_key, size_bytes FROM original_files").fetchall()
    problems: List[str] = []
    checked = 0
    for row in rows:
        cid, sha = row["candidate_id"], row["sha256_hash"]
        expected_key = cv_key(cid, sha, row["file_type"])
        if row["s3_key"] != expected_key:
            problems.append(f"{cid}: s3_key {row['s3_key']} != {expected_key}")
            continue
        blob_row = sconn.execute("SELECT file_data FROM original_files WHERE candidate_id = ?", (cid,)).fetchone()
        if blob_row is None or hashlib.sha256(bytes(blob_row[0] or b"")).hexdigest() != sha:
            problems.append(f"{cid}: source BLOB hash differs from sha256_hash")
        try:
            stored = storage.checksum_sha256(row["s3_key"])
        except Exception as err:
            problems.append(f"{cid}: object not readable: {err}")
            continue
        if stored != sha:
            problems.append(f"{cid}: stored checksum {stored} != {sha}")
        if deep:
            data = storage.get(row["s3_key"])
            if hashlib.sha256(data).hexdigest() != sha or len(data) != row["size_bytes"]:
                problems.append(f"{cid}: downloaded object hash/size differs")
        checked += 1

    expected_keys = {r["s3_key"] for r in rows}
    present = set(storage.list_keys("cvs/"))
    missing = sorted(expected_keys - present)
    extra = sorted(present - expected_keys)
    problems.extend(f"missing object {k}" for k in missing[:MAX_LISTED])
    return {
        "rows": len(rows),
        "checked": checked,
        "deep_download_check": deep,
        "objects_under_cvs_prefix": len(present),
        "missing_objects": missing[:MAX_LISTED],
        # Objects from an earlier rehearsal or from candidates deleted since;
        # listed for clean-up, not a failure of this load.
        "extra_objects": extra[:MAX_LISTED],
        "extra_object_count": len(extra),
        "problems": problems[:MAX_LISTED],
        "status": _status(not problems and not missing),
    }


def _source_orphans(data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Set[str]]:
    candidates = {r["candidate_id"] for r in data["candidates"]}
    jobs = {r["job_id"] for r in data["jobs"]}
    return {
        "match_results_without_candidate": {str(r["id"]) for r in data["match_results"] if r["candidate_id"] not in candidates},
        "match_results_without_job": {str(r["id"]) for r in data["match_results"] if r["job_id"] not in jobs},
        "recruiter_actions_without_candidate": {str(r["id"]) for r in data["recruiter_actions"] if r["candidate_id"] not in candidates},
        "chat_messages_without_candidate": {str(r["id"]) for r in data["candidate_chat_messages"] if r["candidate_id"] not in candidates},
        "original_files_without_candidate": {r["candidate_id"] for r in data["original_files"] if r["candidate_id"] not in candidates},
    }


ORPHAN_SQL = {
    "match_results_without_candidate": "SELECT m.id::text AS k FROM match_results m LEFT JOIN candidates c USING (candidate_id) WHERE c.candidate_id IS NULL",
    "match_results_without_job": "SELECT m.id::text AS k FROM match_results m LEFT JOIN jobs j USING (job_id) WHERE j.job_id IS NULL",
    "recruiter_actions_without_candidate": "SELECT r.id::text AS k FROM recruiter_actions r LEFT JOIN candidates c USING (candidate_id) WHERE c.candidate_id IS NULL",
    "chat_messages_without_candidate": "SELECT m.id::text AS k FROM candidate_chat_messages m LEFT JOIN candidates c USING (candidate_id) WHERE c.candidate_id IS NULL",
    "original_files_without_candidate": "SELECT f.candidate_id AS k FROM original_files f LEFT JOIN candidates c USING (candidate_id) WHERE c.candidate_id IS NULL",
}


def verify_orphans(conn, data) -> Dict[str, Any]:
    source = _source_orphans(data)
    result: Dict[str, Any] = {}
    ok = True
    for name, sql in ORPHAN_SQL.items():
        target = {r["k"] for r in conn.execute(sql).fetchall()}
        new = sorted(target - source[name])
        ok = ok and not new
        result[name] = {"pre_existing": sorted(source[name])[:MAX_LISTED], "pre_existing_count": len(source[name]),
                        "new": new[:MAX_LISTED], "new_count": len(new)}
    result["status"] = _status(ok)
    return result


def _round(value: Any) -> Any:
    return None if value is None else round(float(value), 6)


def _source_aggregates(data) -> Dict[str, Any]:
    def count_by(rows, *keys):
        out: Dict[str, int] = {}
        for r in rows:
            k = "|".join(str(r.get(x)) for x in keys)
            out[k] = out.get(k, 0) + 1
        return dict(sorted(out.items()))

    scores = [r["score"] for r in data["match_results"]]
    agg = {
        "candidates_by_status_source": count_by(data["candidates"], "status", "source"),
        "actions_by_type": count_by(data["recruiter_actions"], "action"),
        "match_scores": {
            "count": len(scores),
            "sum": _round(sum(scores)) if scores else None,
            "avg": _round(sum(scores) / len(scores)) if scores else None,
            "min": _round(min(scores)) if scores else None,
            "max": _round(max(scores)) if scores else None,
        },
        "time_range": {},
    }
    for table in TABLES:
        col = table.timestamp_columns[0]
        column = next(c for c in table.columns if c.name == col)
        values = [canonical(column, r[col]) for r in data[table.name] if r.get(col) is not None]
        agg["time_range"][table.name] = [min(values), max(values)] if values else [None, None]
    return agg


def _target_aggregates(conn) -> Dict[str, Any]:
    def count_by(sql):
        return dict(sorted({r["k"]: r["n"] for r in conn.execute(sql).fetchall()}.items()))

    s = conn.execute("SELECT COUNT(score) AS c, SUM(score) AS s, AVG(score) AS a, MIN(score) AS mi, MAX(score) AS ma FROM match_results").fetchone()
    agg = {
        "candidates_by_status_source": count_by("SELECT COALESCE(status, 'None') || '|' || COALESCE(source, 'None') AS k, COUNT(*) AS n FROM candidates GROUP BY 1"),
        "actions_by_type": count_by("SELECT COALESCE(action, 'None') AS k, COUNT(*) AS n FROM recruiter_actions GROUP BY 1"),
        "match_scores": {"count": s["c"], "sum": _round(s["s"]), "avg": _round(s["a"]), "min": _round(s["mi"]), "max": _round(s["ma"])},
        "time_range": {},
    }
    for table in TABLES:
        col = table.timestamp_columns[0]
        column = next(c for c in table.columns if c.name == col)
        r = conn.execute(f'SELECT MIN("{col}") AS lo, MAX("{col}") AS hi FROM "{table.name}"').fetchone()
        agg["time_range"][table.name] = [canonical(column, r["lo"]), canonical(column, r["hi"])]
    return agg


def verify_aggregates(conn, data) -> Dict[str, Any]:
    source, target = _source_aggregates(data), _target_aggregates(conn)
    diffs = [k for k in source if source[k] != target[k]]
    return {"source": source, "target": target, "differences": diffs, "status": _status(not diffs)}


def verify_sequences(conn) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    ok = True
    for table in TABLES:
        if not table.identity:
            continue
        seq = conn.execute("SELECT pg_get_serial_sequence(%s, %s) AS s", (table.name, table.identity)).fetchone()["s"]
        state = conn.execute(f"SELECT last_value, is_called FROM {seq}").fetchone()
        next_value = state["last_value"] + 1 if state["is_called"] else state["last_value"]
        max_id = conn.execute(f'SELECT MAX("{table.identity}") AS m FROM "{table.name}"').fetchone()["m"]
        good = max_id is None or next_value > max_id
        ok = ok and good
        out[table.name] = {"max_id": max_id, "next_value": next_value, "status": _status(good)}
    out["status"] = _status(ok)
    return out


def verify(report: Dict[str, Any], sconn: sqlite3.Connection, data, excluded: Set[str], deep: bool = True) -> None:
    excluded_counts = report.get("rules", {}).get("excluded_rows", {})
    with db.connection() as conn:
        report["tables"] = verify_tables(conn, data, excluded_counts)
        report["cv_files"] = verify_cv_files(conn, sconn, deep)
        report["orphans"] = verify_orphans(conn, data)
        report["aggregates"] = verify_aggregates(conn, data)
        report["sequences"] = verify_sequences(conn)
    assert set(TABLES_BY_NAME) == set(report["tables"])
