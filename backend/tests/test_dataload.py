"""SQLite -> PostgreSQL + S3 load job and its verification report.

The source is built with the exact DDL of the SQLite version (commit 4dfb9c0)
and the target is a separate PostgreSQL database, so the main test database
is not touched."""
import hashlib
import json
import os
import sqlite3
import tempfile
import unittest

import psycopg

from backend.app.config import settings
from backend.app.dataload import sqlite_to_postgres as loader
from backend.app.db import database as db
from backend.app.services.cv_storage import LocalCVStorage, get_cv_storage, set_cv_storage

SQLITE_DDL = """
CREATE TABLE candidates (candidate_id TEXT PRIMARY KEY, full_name TEXT, email TEXT, phone TEXT, location TEXT,
  roles TEXT, skills TEXT, years_experience REAL, notice_period TEXT, source TEXT DEFAULT 'UPLOADED',
  status TEXT DEFAULT 'COMPLETED', raw_json TEXT, file_hash TEXT, filename TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE original_files (candidate_id TEXT PRIMARY KEY, filename TEXT NOT NULL, file_type TEXT NOT NULL,
  sha256_hash TEXT NOT NULL UNIQUE, file_data BLOB NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, candidate_id TEXT,
  details TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE match_results (id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id TEXT NOT NULL, job_id TEXT NOT NULL,
  score REAL NOT NULL, recommendation TEXT NOT NULL, matched_skills TEXT, missing_skills TEXT, reasoning TEXT,
  score_breakdown TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(candidate_id, job_id));
CREATE TABLE jobs (job_id TEXT PRIMARY KEY, title TEXT NOT NULL, department TEXT DEFAULT '', location TEXT DEFAULT '',
  employment_type TEXT DEFAULT 'Full-time', seniority TEXT DEFAULT 'Mid-level', description TEXT DEFAULT '',
  minimum_years_experience REAL DEFAULT 0.0, required_skills TEXT DEFAULT '[]', preferred_skills TEXT DEFAULT '[]',
  education_requirements TEXT DEFAULT '[]', domain_requirements TEXT DEFAULT '[]', responsibilities TEXT DEFAULT '[]',
  other_constraints TEXT DEFAULT '', source TEXT DEFAULT 'MANUAL', status TEXT DEFAULT 'ACTIVE',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE recruiter_actions (id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id TEXT NOT NULL, job_id TEXT,
  action TEXT NOT NULL, note TEXT DEFAULT '', tag TEXT DEFAULT '', user_id TEXT DEFAULT 'default',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE batch_jobs (batch_id TEXT PRIMARY KEY, job_id TEXT, status TEXT DEFAULT 'QUEUED', total INTEGER DEFAULT 0,
  completed INTEGER DEFAULT 0, processing INTEGER DEFAULT 0, queued INTEGER DEFAULT 0, failed INTEGER DEFAULT 0,
  file_statuses TEXT DEFAULT '[]', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE candidate_chat_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id TEXT NOT NULL, job_id TEXT,
  role TEXT NOT NULL, content TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (candidate_id) REFERENCES candidates(candidate_id) ON DELETE CASCADE);
"""

PDF = b"%PDF-1.4\n" + bytes(range(256)) * 4
DOCX = b"PK\x03\x04 fake docx"


def build_source(path: str, *, bad_json: bool = False, bad_blob: bool = False, chat_orphan: bool = False) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(SQLITE_DDL)
    conn.execute(
        "INSERT INTO jobs (job_id, title, required_skills, minimum_years_experience, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("JOB-001", "Backend Engineer", json.dumps(["Python", "PostgreSQL"]), 5, "2026-10-01 10:00:00", "2026-10-02T11:30:15.123456"),
    )
    conn.execute("INSERT INTO jobs (job_id, title) VALUES ('JOB-002', 'SRE')")
    cands = [
        ("CAND-AAAA0001", "Asha K", "UPLOADED", {"candidate_id": "CAND-AAAA0001", "full_name": "Asha K", "skills": ["Python"], "score": 1.0}),
        ("CAND-BBBB0002", "Mock Person", "MOCK", {"candidate_id": "CAND-BBBB0002", "full_name": "Mock Person"}),
        ("CAND-CCCC0003", "Nul\x00 Name", "UPLOADED", {"candidate_id": "CAND-CCCC0003", "summary": "has \x00 nul"}),
    ]
    for cid, name, source, raw in cands:
        conn.execute(
            "INSERT INTO candidates (candidate_id, full_name, roles, skills, years_experience, source, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (cid, name, json.dumps(["Engineer"]), json.dumps(raw.get("skills", [])), 4.5, source,
             "{not json" if bad_json and cid == "CAND-AAAA0001" else json.dumps(raw)),
        )
    for cid, fname, ftype, data in [("CAND-AAAA0001", "asha.pdf", "pdf", PDF), ("CAND-CCCC0003", "c.docx", "docx", DOCX)]:
        sha = hashlib.sha256(data).hexdigest()
        stored = data + b"corrupt" if bad_blob and cid == "CAND-AAAA0001" else data
        conn.execute("INSERT INTO original_files (candidate_id, filename, file_type, sha256_hash, file_data) VALUES (?, ?, ?, ?, ?)",
                     (cid, fname, ftype, sha, stored))
    conn.execute("INSERT INTO match_results (candidate_id, job_id, score, recommendation, matched_skills, score_breakdown) VALUES ('CAND-AAAA0001', 'JOB-001', 87.5, 'STRONG MATCH', '[\"Python\"]', '{\"skills\": 40.25}')")
    conn.execute("INSERT INTO match_results (candidate_id, job_id, score, recommendation) VALUES ('CAND-BBBB0002', 'JOB-001', 42.0, 'NOT MATCHED')")
    conn.execute("INSERT INTO match_results (candidate_id, job_id, score, recommendation) VALUES ('CAND-AAAA0001', 'JOB-GONE', 50.0, 'REVIEW')")
    conn.execute("INSERT INTO recruiter_actions (candidate_id, job_id, action, note) VALUES ('CAND-AAAA0001', 'JOB-001', 'SHORTLIST', 'good')")
    conn.execute("INSERT INTO recruiter_actions (candidate_id, action) VALUES ('CAND-BBBB0002', 'REJECT')")
    conn.execute("INSERT INTO candidate_chat_messages (candidate_id, role, content) VALUES ('CAND-AAAA0001', 'user', 'Summarise')")
    conn.execute("INSERT INTO candidate_chat_messages (candidate_id, role, content) VALUES ('CAND-BBBB0002', 'assistant', 'Mock chat')")
    if chat_orphan:
        conn.execute("INSERT INTO candidate_chat_messages (candidate_id, role, content) VALUES ('CAND-DELETED', 'user', 'orphan')")
    for i in range(3):
        conn.execute("INSERT INTO audit_logs (event_type, candidate_id, details) VALUES ('SAVE_CANDIDATE', ?, 'x')", (cands[i][0],))
    conn.execute("INSERT INTO batch_jobs (batch_id, total, completed, file_statuses) VALUES ('BATCH-1', 1, 1, '[{\"filename\": \"a.pdf\"}]')")
    conn.commit()
    conn.close()


class TestSqliteToPostgres(unittest.TestCase):
    TARGET_DB = "raas_load_test"

    @classmethod
    def setUpClass(cls):
        base = settings.DATABASE_URL
        cls.saved_url = base
        cls.target_url = base.rsplit("/", 1)[0] + "/" + cls.TARGET_DB
        with psycopg.connect(base, autocommit=True) as conn:
            conn.execute(f"DROP DATABASE IF EXISTS {cls.TARGET_DB}")
            conn.execute(f"CREATE DATABASE {cls.TARGET_DB}")
        db.close_pool()
        settings.DATABASE_URL = cls.target_url
        cls.saved_storage = get_cv_storage()
        cls.cv_dir = tempfile.mkdtemp(prefix="raas-load-cv-")
        set_cv_storage(LocalCVStorage(cls.cv_dir))

    @classmethod
    def tearDownClass(cls):
        db.close_pool()
        settings.DATABASE_URL = cls.saved_url
        set_cv_storage(cls.saved_storage)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="raas-src-")

    def source(self, **kw) -> str:
        path = os.path.join(self.tmp, "cv_screening.db")
        build_source(path, **kw)
        return path

    def run_job(self, *argv):
        return loader.run(loader.parse_args(list(argv)))

    def test_load_rules_and_verification(self):
        src = self.source()

        # 1. Full load into an empty database.
        report = self.run_job("--sqlite", src, "--truncate")
        self.assertEqual(report["result"], "PASS", json.dumps(report, indent=1, default=str)[:3000])
        self.assertEqual(report["tables"]["candidates"]["target_count"], 3)
        self.assertEqual(report["tables"]["match_results"]["hash_matched"], 3)
        self.assertEqual(report["rules"]["nul_characters_removed"]["rows"], 1)
        self.assertEqual(report["orphans"]["match_results_without_job"]["pre_existing_count"], 1)
        self.assertEqual(report["cv_files"]["checked"], 2)
        self.assertEqual(report["source"]["integrity_check"], "ok")

        with db.connection() as conn:
            row = conn.execute("SELECT s3_key, size_bytes FROM original_files WHERE candidate_id = 'CAND-AAAA0001'").fetchone()
            self.assertEqual(row["s3_key"], f"cvs/CAND-AAAA0001/{hashlib.sha256(PDF).hexdigest()}.pdf")
            self.assertEqual(row["size_bytes"], len(PDF))
            raw = conn.execute("SELECT raw_json, full_name FROM candidates WHERE candidate_id = 'CAND-CCCC0003'").fetchone()
            self.assertEqual(raw["raw_json"]["summary"], "has  nul")
            self.assertEqual(raw["full_name"], "Nul Name")
            # New rows get ids after the loaded ones.
            new_id = conn.execute("INSERT INTO recruiter_actions (candidate_id, action) VALUES ('CAND-AAAA0001', 'NOTE') RETURNING id").fetchone()["id"]
            self.assertEqual(new_id, 3)
            conn.execute("DELETE FROM recruiter_actions WHERE id = %s", (new_id,))
        self.assertEqual(get_cv_storage().get(row["s3_key"]), PDF)
        self.assertEqual(report["sequences"]["status"], "PASS")

        # 2. A second load refuses a non-empty target.
        again = self.run_job("--sqlite", src)
        self.assertEqual(again["result"], "FAIL")
        self.assertIn("not empty", again["errors"][0])

        # 3. Rehearsal rerun with the seed-data rule.
        excl = self.run_job("--sqlite", src, "--truncate", "--exclude-source", "mock")
        self.assertEqual(excl["result"], "PASS", json.dumps(excl, indent=1, default=str)[:3000])
        self.assertEqual(excl["rules"]["excluded_rows"]["candidates"], 1)
        self.assertEqual(excl["rules"]["excluded_rows"]["match_results"], 1)
        self.assertEqual(excl["rules"]["excluded_rows"]["candidate_chat_messages"], 1)
        self.assertEqual(excl["tables"]["candidates"]["target_count"], 2)

        # 4. Verification catches a changed row and a damaged CV object.
        with db.connection() as conn:
            conn.execute("UPDATE candidates SET full_name = 'Changed' WHERE candidate_id = 'CAND-AAAA0001'")
        key = f"cvs/CAND-AAAA0001/{hashlib.sha256(PDF).hexdigest()}.pdf"
        with open(os.path.join(self.cv_dir, key), "wb") as fh:
            fh.write(b"tampered")
        check = self.run_job("--sqlite", src, "--verify-only", "--exclude-source", "MOCK")
        self.assertEqual(check["result"], "FAIL")
        self.assertEqual(check["tables"]["candidates"]["hash_mismatched"], ["CAND-AAAA0001"])
        self.assertEqual(check["cv_files"]["status"], "FAIL")

    def test_bad_json_stops_before_writing(self):
        report = self.run_job("--sqlite", self.source(bad_json=True), "--truncate")
        self.assertEqual(report["result"], "FAIL")
        self.assertTrue(any("raw_json is not valid JSON" in e for e in report["errors"]), report["errors"])
        self.assertNotIn("tables", report)

    def test_blob_hash_mismatch_stops(self):
        report = self.run_job("--sqlite", self.source(bad_blob=True), "--truncate")
        self.assertEqual(report["result"], "FAIL")
        self.assertTrue(any("BLOB SHA-256" in e for e in report["errors"]), report["errors"])

    def test_chat_orphans_need_a_decision(self):
        src = self.source(chat_orphan=True)
        report = self.run_job("--sqlite", src, "--truncate")
        self.assertEqual(report["result"], "FAIL")
        self.assertIn("--drop-chat-orphans", report["errors"][0])
        report = self.run_job("--sqlite", src, "--truncate", "--drop-chat-orphans")
        self.assertEqual(report["result"], "PASS", report.get("errors"))
        self.assertEqual(len(report["rules"]["chat_orphans_dropped"]), 1)


if __name__ == "__main__":
    unittest.main()
