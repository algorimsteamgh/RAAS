"""One-off load of the RAASHiring SQLite database into PostgreSQL (RDS), with
the CV files moved from database BLOBs to S3, followed by the verification
report of RAAS-MIG-05. Runs as the `migrate` ECS task in the AWS account, so
no candidate data passes through a personal machine.

    python -m backend.app.dataload.sqlite_to_postgres \\
        --sqlite s3://raas-cvs-007477962703-ap-southeast-1/migration/cv_screening.db \\
        --report s3://raas-cvs-007477962703-ap-southeast-1/migration/reports/ \\
        [--exclude-source MOCK] [--truncate]

    # verification only (target already loaded), e.g. after the cut-over load:
    python -m backend.app.dataload.sqlite_to_postgres --sqlite s3://.../cv_screening.db --verify-only

Steps
  1. Fetch the SQLite file; record its SHA-256 and size.
  2. Pre-checks: PRAGMA integrity_check (must be ok), PRAGMA foreign_key_check,
     per-table counts.
  3. Schema: Alembic upgrade to head (the migrations the app uses).
  4. Target must be empty; --truncate empties it first (rehearsals).
  5. Convert every row strictly (bad JSON, timestamps or numbers stop the job
     before anything is written, with every problem listed).
  6. Upload each CV to S3 at cvs/{candidate_id}/{sha256}.{ext} with SSE-KMS
     and a SHA-256 checksum (S3 rejects a corrupted upload). A BLOB whose hash
     does not match original_files.sha256_hash stops the job.
  7. Insert all rows in one transaction, in dependency order; reset the
     identity sequences.
  8. Verify (see verify.py) and write the JSON report; exit 1 if any check fails.

Seed-data rule (decision Q8): --exclude-source MOCK leaves out candidates with
that source and their files, matches, actions, chat and audit rows. The
excluded counts are part of the report.
"""
import argparse
import hashlib
import json
import logging
import os
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from psycopg.types.json import Jsonb

from backend.app.dataload import verify
from backend.app.dataload.tables import TABLES, ConversionError, Table, has_nul, parse_value, pk_of
from backend.app.db import database as db
from backend.app.services.cv_storage import content_type_for, cv_key, get_cv_storage

logger = logging.getLogger("raas.dataload")

TARGET_TABLES = [t.name for t in TABLES] + ["batch_files"]


# --------------------------------------------------------------------------- source
def fetch_source(uri: str, workdir: str) -> str:
    if not uri.startswith("s3://"):
        return uri
    import boto3

    bucket, _, key = uri[5:].partition("/")
    path = os.path.join(workdir, os.path.basename(key) or "source.db")
    logger.info("Downloading %s", uri)
    boto3.client("s3", region_name=os.getenv("AWS_REGION", "ap-southeast-1")).download_file(bucket, key, path)
    return path


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def open_sqlite(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def source_tables(conn: sqlite3.Connection) -> Dict[str, List[str]]:
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    return {n: [r[1] for r in conn.execute(f'PRAGMA table_info("{n}")')] for n in names}


def precheck(conn: sqlite3.Connection, path: str) -> Dict[str, Any]:
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
    tables = source_tables(conn)
    counts = {t.name: (conn.execute(f'SELECT COUNT(*) FROM "{t.name}"').fetchone()[0] if t.name in tables else None) for t in TABLES}
    by_source = {}
    if "candidates" in tables:
        by_source = {str(r[0]): r[1] for r in conn.execute("SELECT source, COUNT(*) FROM candidates GROUP BY source")}
    cv_mb = None
    if "original_files" in tables:
        cv_mb = conn.execute("SELECT COALESCE(SUM(LENGTH(file_data)), 0) / 1048576.0 FROM original_files").fetchone()[0]
    return {
        "path_sha256": file_sha256(path),
        "size_bytes": os.path.getsize(path),
        "integrity_check": integrity,
        "foreign_key_violations": [list(r) for r in fk_rows],
        "tables_present": sorted(tables),
        "missing_tables": [t.name for t in TABLES if t.name not in tables],
        "missing_columns": {
            t.name: [c for c in t.column_names if c not in tables[t.name]]
            for t in TABLES if t.name in tables and any(c not in tables[t.name] for c in t.column_names)
        },
        "counts": counts,
        "candidates_by_source": by_source,
        "cv_megabytes": round(cv_mb, 3) if cv_mb is not None else None,
    }


def excluded_candidate_ids(conn: sqlite3.Connection, sources: List[str]) -> Set[str]:
    if not sources:
        return set()
    wanted = [s.upper() for s in sources]
    marks = ",".join("?" * len(wanted))
    return {r[0] for r in conn.execute(f"SELECT candidate_id FROM candidates WHERE UPPER(source) IN ({marks})", wanted)}


def read_rows(conn: sqlite3.Connection, table: Table, available: List[str]) -> List[Dict[str, Any]]:
    cols = [c for c in table.column_names if c in available]
    order = ", ".join(f'"{k}"' for k in table.pk)
    rows = conn.execute(f'SELECT {", ".join(chr(34) + c + chr(34) for c in cols)} FROM "{table.name}" ORDER BY {order}').fetchall()
    return [{c: (row[c] if c in cols else None) for c in table.column_names} for row in rows]


def convert_rows(table: Table, rows: List[Dict[str, Any]], errors: List[str], nul_rows: List[str]) -> List[Dict[str, Any]]:
    out = []
    for raw in rows:
        converted = {}
        for column in table.columns:
            try:
                converted[column.name] = parse_value(column, raw.get(column.name))
            except ConversionError as err:
                errors.append(f"{table.name}[{pk_of(table, raw)}].{err}")
        if any(has_nul(v) for v in raw.values()):
            nul_rows.append(f"{table.name}[{pk_of(table, raw)}]")
        out.append(converted)
    return out


def filter_excluded(table: Table, rows: List[Dict[str, Any]], excluded: Set[str]) -> Tuple[List[Dict[str, Any]], int]:
    if not excluded or not table.candidate_column:
        return rows, 0
    kept = [r for r in rows if r.get(table.candidate_column) not in excluded]
    return kept, len(rows) - len(kept)


# --------------------------------------------------------------------------- target
def target_counts(conn) -> Dict[str, int]:
    return {t: conn.execute(f'SELECT COUNT(*) AS n FROM "{t}"').fetchone()["n"] for t in TARGET_TABLES}


def insert_rows(conn, table: Table, rows: List[Dict[str, Any]], extra: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
    if not rows:
        return
    cols = table.column_names + (list(next(iter(extra.values())).keys()) if extra else [])
    sql = f'INSERT INTO "{table.name}" ({", ".join(chr(34) + c + chr(34) for c in cols)}) VALUES ({", ".join(["%s"] * len(cols))})'
    json_cols = {c.name for c in table.columns if c.kind == "json"}
    params = []
    for row in rows:
        values = [Jsonb(row[c]) if c in json_cols and row[c] is not None else row.get(c) for c in table.column_names]
        if extra:
            values += list(extra[pk_of(table, row)].values())
        params.append(values)
    with conn.cursor() as cur:
        cur.executemany(sql, params)


def reset_identities(conn) -> None:
    for table in TABLES:
        if table.identity:
            conn.execute(
                f"SELECT setval(pg_get_serial_sequence('{table.name}', '{table.identity}'), "
                f"COALESCE((SELECT MAX({table.identity}) FROM {table.name}), 0) + 1, false)"
            )


def upload_cvs(sqlite_conn: sqlite3.Connection, files: List[Dict[str, Any]], errors: List[str]) -> Dict[str, Dict[str, Any]]:
    """Stream each BLOB to storage. Returns {candidate_id: {s3_key, size_bytes}}."""
    storage = get_cv_storage()
    placed: Dict[str, Dict[str, Any]] = {}
    started = time.monotonic()
    for i, f in enumerate(files, 1):
        cid = f["candidate_id"]
        blob = sqlite_conn.execute("SELECT file_data FROM original_files WHERE candidate_id = ?", (cid,)).fetchone()[0]
        data = bytes(blob) if blob is not None else b""
        actual = hashlib.sha256(data).hexdigest()
        if actual != f["sha256_hash"]:
            errors.append(f"original_files[{cid}]: BLOB SHA-256 {actual} does not match sha256_hash {f['sha256_hash']}")
            continue
        key = cv_key(cid, actual, f["file_type"])
        storage.put(key, data, content_type_for(f["file_type"]), actual)
        placed[cid] = {"s3_key": key, "size_bytes": len(data)}
        if i % 100 == 0:
            logger.info("Uploaded %d/%d CV files (%.0fs)", i, len(files), time.monotonic() - started)
    logger.info("Uploaded %d CV files in %.0fs", len(placed), time.monotonic() - started)
    return placed


# --------------------------------------------------------------------------- report
def write_report(report: Dict[str, Any], destination: Optional[str]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    body = json.dumps(report, indent=2, default=str, ensure_ascii=False)
    local = os.path.join(tempfile.gettempdir(), f"raas-load-report-{stamp}.json")
    with open(local, "w", encoding="utf-8") as fh:
        fh.write(body)
    if destination and destination.startswith("s3://"):
        import boto3

        bucket, _, prefix = destination[5:].partition("/")
        key = (prefix.rstrip("/") + "/" if prefix else "") + f"load-report-{stamp}.json"
        boto3.client("s3", region_name=os.getenv("AWS_REGION", "ap-southeast-1")).put_object(
            Bucket=bucket, Key=key, Body=body.encode(), ContentType="application/json", ServerSideEncryption="aws:kms"
        )
        return f"s3://{bucket}/{key}"
    if destination:
        with open(destination, "w", encoding="utf-8") as fh:
            fh.write(body)
        return destination
    return local


def print_summary(report: Dict[str, Any]) -> None:
    lines = ["", "=" * 78, f"RAASHiring data load: {report['result']}", "=" * 78]
    lines.append(f"{'table':<26}{'source':>9}{'excluded':>10}{'target':>9}{'hash ok':>9}  status")
    for name, t in report.get("tables", {}).items():
        lines.append(
            f"{name:<26}{str(t.get('source_count')):>9}{str(t.get('excluded', 0)):>10}{str(t.get('target_count')):>9}"
            f"{str(t.get('hash_matched')):>9}  {t.get('status')}"
        )
    for check in ("cv_files", "orphans", "aggregates", "sequences"):
        if check in report:
            lines.append(f"{check:<26}{report[check].get('status')}")
    for err in report.get("errors", [])[:50]:
        lines.append(f"  ERROR {err}")
    lines.append("=" * 78)
    print("\n".join(lines), flush=True)


# --------------------------------------------------------------------------- main
def run(args: argparse.Namespace) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "job": "sqlite_to_postgres",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "source_uri": args.sqlite,
        "rules": {"exclude_sources": [s.upper() for s in args.exclude_source], "verify_only": args.verify_only},
        "errors": [],
    }
    with tempfile.TemporaryDirectory(prefix="raas-load-") as workdir:
        path = fetch_source(args.sqlite, workdir)
        sconn = open_sqlite(path)
        report["source"] = pre = precheck(sconn, path)
        logger.info("Source: %s, integrity=%s, counts=%s", pre["path_sha256"], pre["integrity_check"], pre["counts"])
        if pre["integrity_check"] != "ok":
            report["errors"].append(f"SQLite integrity_check: {pre['integrity_check']}")
            return _finish(report)

        available = source_tables(sconn)
        excluded = excluded_candidate_ids(sconn, args.exclude_source)
        conversion_errors: List[str] = []
        nul_rows: List[str] = []
        data: Dict[str, List[Dict[str, Any]]] = {}
        excluded_counts: Dict[str, int] = {}
        for table in TABLES:
            raw = read_rows(sconn, table, available[table.name]) if table.name in available else []
            kept, dropped = filter_excluded(table, raw, excluded)
            excluded_counts[table.name] = dropped
            data[table.name] = convert_rows(table, kept, conversion_errors, nul_rows)
        report["rules"]["excluded_rows"] = excluded_counts
        report["rules"]["nul_characters_removed"] = {"rows": len(nul_rows), "examples": nul_rows[:20]}
        if conversion_errors:
            report["errors"].extend(conversion_errors)
            return _finish(report)

        # candidate_chat_messages has a foreign key in PostgreSQL (as declared in
        # SQLite, where it was not enforced): orphans cannot be loaded.
        candidate_ids = {r["candidate_id"] for r in data["candidates"]}
        chat_orphans = [r["id"] for r in data["candidate_chat_messages"] if r["candidate_id"] not in candidate_ids]
        if chat_orphans:
            if not args.drop_chat_orphans:
                report["errors"].append(
                    f"{len(chat_orphans)} chat message(s) reference missing candidates (ids {chat_orphans[:20]}); "
                    "rerun with --drop-chat-orphans to leave them out"
                )
                return _finish(report)
            data["candidate_chat_messages"] = [r for r in data["candidate_chat_messages"] if r["candidate_id"] in candidate_ids]
        report["rules"]["chat_orphans_dropped"] = chat_orphans if args.drop_chat_orphans else []

        if not args.skip_migrate and not args.verify_only:
            from backend.app.db.migrate import upgrade

            upgrade()

        if not args.verify_only:
            with db.connection() as conn:
                counts = target_counts(conn)
                if any(counts.values()):
                    if not args.truncate:
                        report["errors"].append(f"Target is not empty ({counts}); rerun with --truncate to replace it")
                        return _finish(report)
                    logger.warning("Truncating target tables: %s", counts)
                    conn.execute("TRUNCATE " + ", ".join(f'"{t}"' for t in TARGET_TABLES) + " RESTART IDENTITY CASCADE")

            upload_errors: List[str] = []
            placed = upload_cvs(sconn, data["original_files"], upload_errors)
            if upload_errors:
                report["errors"].extend(upload_errors)
                return _finish(report)

            started = time.monotonic()
            with db.connection() as conn:
                for table in TABLES:
                    extra = placed if table.name == "original_files" else None
                    insert_rows(conn, table, data[table.name], extra)
                    logger.info("Loaded %s: %d rows", table.name, len(data[table.name]))
                reset_identities(conn)
            report["load_seconds"] = round(time.monotonic() - started, 1)

        verify.verify(report, sconn, data, excluded, deep=not args.no_deep_cv_check)
        sconn.close()
    return _finish(report)


def _finish(report: Dict[str, Any]) -> Dict[str, Any]:
    failed = bool(report["errors"]) or any(
        isinstance(v, dict) and v.get("status") == "FAIL"
        for v in list(report.get("tables", {}).values()) + [report.get(k, {}) for k in ("cv_files", "orphans", "aggregates", "sequences")]
    )
    report["result"] = "FAIL" if failed else "PASS"
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    return report


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sqlite", required=True, help="SQLite file: local path or s3://bucket/key")
    p.add_argument("--report", help="Where to write the JSON report: s3://bucket/prefix/ or a local path")
    p.add_argument("--exclude-source", action="append", default=[], help="Leave out candidates with this source (repeatable), e.g. MOCK")
    p.add_argument("--truncate", action="store_true", help="Empty the target tables first (rehearsals)")
    p.add_argument("--verify-only", action="store_true", help="Do not load; verify the target against the source")
    p.add_argument("--skip-migrate", action="store_true", help="Do not run Alembic first")
    p.add_argument("--drop-chat-orphans", action="store_true", help="Leave out chat messages whose candidate no longer exists (listed in the report)")
    p.add_argument("--no-deep-cv-check", action="store_true", help="Compare stored S3 checksums only, without downloading each CV")
    return p.parse_args(argv)


def main(argv: List[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = parse_args(argv)
    report = run(args)
    where = write_report(report, args.report)
    print_summary(report)
    logger.info("Report written to %s", where)
    db.close_pool()
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
