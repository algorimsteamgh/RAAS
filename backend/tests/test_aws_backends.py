"""S3 CV storage, the Bedrock provider, and SQS batch processing.

AWS is simulated: moto for S3 and SQS, botocore's Stubber for Bedrock (it
checks every request against the real API model). PostgreSQL is real."""
import asyncio
import base64
import hashlib
import json
import time
import unittest

import boto3
from botocore.exceptions import ClientError
from botocore.stub import ANY, Stubber
from fastapi.testclient import TestClient
from moto import mock_aws

from backend.app.config import settings
from backend.app.db import database as db
from backend.app.main import app
from backend.app.services import batch_service
from backend.app.services.cv_storage import LocalCVStorage, S3CVStorage, cv_key, get_cv_storage, set_cv_storage
from backend.app.services.llm.bedrock_client import BedrockClient
from backend.app.services.llm.schemas import CV_EXTRACTION_SCHEMA
from backend.app.worker import Worker

REGION = "ap-southeast-1"
CV_TEXT = (
    "Priya Raman\nBengaluru, Karnataka, India\npriya.raman@example.com\n\n"
    "EXPERIENCE\nSenior Backend Engineer, Acme Corp\nJan 2020 - Present\n"
    "Built Python and PostgreSQL services on AWS.\n\nSKILLS\nPython, PostgreSQL, AWS, Docker\n"
)


def run(coro):
    return asyncio.run(coro)


class TestS3CVStorage(unittest.TestCase):
    @mock_aws
    def test_put_get_checksum_delete(self):
        s3 = boto3.client("s3", region_name=REGION)
        s3.create_bucket(Bucket="cvs", CreateBucketConfiguration={"LocationConstraint": REGION})
        kms = boto3.client("kms", region_name=REGION)
        key_id = kms.create_key()["KeyMetadata"]["Arn"]
        storage = S3CVStorage("cvs", kms_key_id=key_id, client=s3)

        data = b"%PDF-1.4 fake cv"
        sha = hashlib.sha256(data).hexdigest()
        key = cv_key("CAND-ABC12345", sha, "pdf")
        self.assertEqual(key, f"cvs/CAND-ABC12345/{sha}.pdf")

        storage.put(key, data, "application/pdf", sha)
        self.assertEqual(storage.get(key), data)
        self.assertEqual(storage.checksum_sha256(key), sha)
        head = s3.head_object(Bucket="cvs", Key=key)
        self.assertEqual(head["ServerSideEncryption"], "aws:kms")

        storage.delete(key)
        with self.assertRaises(ClientError):
            s3.get_object(Bucket="cvs", Key=key)

    @mock_aws
    def test_put_rejects_wrong_checksum(self):
        s3 = boto3.client("s3", region_name=REGION)
        s3.create_bucket(Bucket="cvs", CreateBucketConfiguration={"LocationConstraint": REGION})
        storage = S3CVStorage("cvs", client=s3)
        with self.assertRaises(ValueError):
            storage.put("cvs/x/y.pdf", b"real bytes", "application/pdf", hashlib.sha256(b"other").hexdigest())

    def test_local_storage_blocks_path_traversal(self):
        storage = LocalCVStorage(settings.CV_LOCAL_DIR)
        with self.assertRaises(ValueError):
            storage.put("../../etc/passwd", b"x", "text/plain")


def _converse_response(content, stop_reason="end_turn"):
    return {
        "output": {"message": {"role": "assistant", "content": content}},
        "stopReason": stop_reason,
        "usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
        "metrics": {"latencyMs": 12},
    }


class TestBedrockClient(unittest.TestCase):
    def setUp(self):
        self.runtime = boto3.client("bedrock-runtime", region_name=REGION, aws_access_key_id="x", aws_secret_access_key="x")
        self.stub = Stubber(self.runtime)
        self.client = BedrockClient(model_id="amazon.nova-lite-v1:0", client=self.runtime)

    def tearDown(self):
        self.stub.deactivate()

    def test_generate_json_uses_forced_tool(self):
        tool_input = {"name": "Priya Raman", "employment_history": [], "skills": ["Python"]}
        self.stub.add_response(
            "converse",
            _converse_response([{"toolUse": {"toolUseId": "t1", "name": "record_candidate_profile", "input": tool_input}}], "tool_use"),
            {
                "modelId": "amazon.nova-lite-v1:0",
                "messages": ANY,
                "system": [{"text": "sys"}],
                "inferenceConfig": {"temperature": 0.0, "maxTokens": settings.BEDROCK_MAX_TOKENS},
                "toolConfig": {
                    "tools": [{"toolSpec": {"name": "record_candidate_profile", "description": ANY, "inputSchema": {"json": CV_EXTRACTION_SCHEMA}}}],
                    "toolChoice": {"tool": {"name": "record_candidate_profile"}},
                },
            },
        )
        with self.stub:
            result = run(self.client.generate_json("cv text", "sys", json_schema=CV_EXTRACTION_SCHEMA, schema_name="record_candidate_profile"))
        self.assertEqual(result, tool_input)

    def test_tool_choice_fallback_to_any(self):
        self.stub.add_client_error("converse", "ValidationException", "This model doesn't support the toolChoice.tool field")
        self.stub.add_response(
            "converse",
            _converse_response([{"toolUse": {"toolUseId": "t1", "name": "record_job_requirements", "input": {"title": "SRE"}}}], "tool_use"),
            {"modelId": ANY, "messages": ANY, "inferenceConfig": ANY,
             "toolConfig": {"tools": ANY, "toolChoice": {"any": {}}}},
        )
        with self.stub:
            result = run(self.client.generate_json("jd", json_schema={"type": "object", "properties": {}}, schema_name="record_job_requirements"))
        self.assertEqual(result, {"title": "SRE"})

    def test_text_answer_is_parsed_as_json(self):
        self.stub.add_response("converse", _converse_response([{"text": "```json\n{\"a\": 1,}\n```"}]))
        with self.stub:
            self.assertEqual(run(self.client.generate_json("x")), {"a": 1})

    def test_truncated_tool_output_raises(self):
        self.stub.add_response("converse", _converse_response([{"text": "partial"}], "max_tokens"))
        with self.stub, self.assertRaises(Exception):
            run(self.client.generate_json("x", json_schema={"type": "object"}, schema_name="t"))

    def test_chat_with_guardrail(self):
        settings.BEDROCK_GUARDRAIL_ID = "gr-123"
        try:
            self.stub.add_response(
                "converse",
                _converse_response([{"text": "Here is a summary."}]),
                {
                    "modelId": "amazon.nova-lite-v1:0",
                    "messages": ANY,
                    "system": ANY,
                    "inferenceConfig": {"temperature": 0.3, "maxTokens": ANY},
                    "guardrailConfig": {"guardrailIdentifier": "gr-123", "guardrailVersion": settings.BEDROCK_GUARDRAIL_VERSION, "trace": "disabled"},
                },
            )
            with self.stub:
                text = run(self.client.generate_text("question", "system", temperature=0.3, use_guardrail=True))
            self.assertEqual(text, "Here is a summary.")
        finally:
            settings.BEDROCK_GUARDRAIL_ID = None

    def test_health_reports_access_denied_as_model_missing(self):
        self.stub.add_client_error("converse", "AccessDeniedException", "no model access")
        with self.stub:
            health = run(self.client.health())
        self.assertEqual(health["status"], "connected_model_missing")


class TestOriginalFileRoundTrip(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_upload_download_delete(self):
        content = CV_TEXT.encode() + b"\nunique-roundtrip"
        res = self.client.post("/api/upload-cv?duplicate_action=replace", files={"file": ("priya.txt", content, "text/plain")})
        self.assertEqual(res.status_code, 200, res.text)
        cand_id = res.json()["candidate_id"]

        meta = db.get_original_file(cand_id)
        sha = hashlib.sha256(content).hexdigest()
        self.assertEqual(meta["s3_key"], f"cvs/{cand_id}/{sha}.txt")
        self.assertEqual(meta["size_bytes"], len(content))

        dl = self.client.get(f"/api/candidates/{cand_id}/original-file")
        self.assertEqual(dl.status_code, 200)
        self.assertEqual(dl.content, content)

        dup = self.client.post("/api/upload-cv", files={"file": ("again.txt", content, "text/plain")})
        self.assertEqual(dup.status_code, 409)
        self.assertEqual(dup.json()["existing_candidate_id"], cand_id)

        self.assertEqual(self.client.delete(f"/api/candidates/{cand_id}").status_code, 200)
        self.assertIsNone(get_cv_storage().checksum_sha256(meta["s3_key"]))

    def test_nul_characters_are_stripped(self):
        content = (CV_TEXT + "\x00 hidden nul").encode() + b"\nunique-nul"
        res = self.client.post("/api/upload-cv?duplicate_action=replace", files={"file": ("nul.txt", content, "text/plain")})
        self.assertEqual(res.status_code, 200, res.text)
        self.client.delete(f"/api/candidates/{res.json()['candidate_id']}")


class TestDemoDataSwitch(unittest.TestCase):
    def test_load_mock_refused_when_seed_off(self):
        settings.SEED_DEMO_DATA = False
        try:
            res = TestClient(app).post("/api/dataset/load-mock")
            self.assertEqual(res.status_code, 403)
        finally:
            settings.SEED_DEMO_DATA = True


class TestInlineBatch(unittest.TestCase):
    def test_batch_upload_inline(self):
        # The context manager keeps one event loop alive, as uvicorn does, so
        # the inline batch task keeps running between requests.
        with TestClient(app) as client:
            files = [
                ("files", ("a.txt", (CV_TEXT + "\ninline-a").encode(), "text/plain")),
                ("files", ("b.xyz", b"not a cv", "application/octet-stream")),
            ]
            res = client.post("/api/batch-upload", files=files)
            self.assertEqual(res.status_code, 200, res.text)
            batch_id = res.json()["batch_id"]
            self.assertEqual(res.json()["total"], 2)

            status = None
            for _ in range(100):
                status = client.get(f"/api/batch-status/{batch_id}").json()
                if status.get("status") == "COMPLETE":
                    break
                time.sleep(0.1)
            self.assertEqual(status.get("status"), "COMPLETE", status)
            by_name = {f["filename"]: f for f in status["files"]}
            self.assertEqual(by_name["a.txt"]["status"], "COMPLETED")
            self.assertEqual(by_name["b.xyz"]["status"], "FAILED")
            self.assertEqual(status["completed"], 1)
            self.assertEqual(status["failed"], 1)

            events = client.get(f"/api/batch-progress/{batch_id}").text
            self.assertIn("event: complete", events)
        db.delete_candidate(by_name["a.txt"]["candidate_id"])


class TestRemoveSource(unittest.TestCase):
    def test_remove_demo_source_keeps_everything_else(self):
        from backend.app.dataload import remove_source

        ids = []
        for i in range(3):
            cid = f"CAND-TDEMO{i:03d}"
            db.save_candidate_record({"candidate_id": cid, "full_name": f"Demo {i}", "skills": ["x"]}, source="TESTDEMO")
            ids.append(cid)
        db.save_recruiter_action(ids[0], "shortlist", note="demo")
        before = {r["candidate_id"] for r in db.list_candidates(None)} - set(ids)

        with self.assertRaises(ValueError):
            remove_source.remove_source("UPLOADED", "no")
        with self.assertRaises(ValueError):
            remove_source.remove_source("TESTDEMO", " ")

        dry = remove_source.remove_source("TESTDEMO", "test cleanup", dry_run=True)
        self.assertEqual(dry["candidates_to_remove"], 3)
        self.assertEqual(sorted(dry["candidate_ids"]), ids)
        self.assertEqual(len([c for c in db.list_candidates(None) if c["candidate_id"] in ids]), 3)

        done = remove_source.remove_source("TESTDEMO", "test cleanup")
        self.assertEqual(done["result"], "PASS", done["checks"])
        self.assertEqual(done["removed_candidates"], 3)
        self.assertNotIn("TESTDEMO", done["after"]["candidates_by_source"])
        self.assertEqual({r["candidate_id"] for r in db.list_candidates(None)}, before)

        record = [r for r in remove_source.cleanup_records() if r.get("source") == "TESTDEMO"][-1]
        self.assertEqual(record["removed_candidates"], 3)
        self.assertEqual(record["candidate_ids"], ids)
        self.assertEqual(record["reason"], "test cleanup")


class TestSqsBatch(unittest.TestCase):
    @mock_aws
    def test_enqueue_and_worker(self):
        sqs = boto3.client("sqs", region_name=REGION)
        queue_url = sqs.create_queue(QueueName="raas-prod-batch")["QueueUrl"]
        batch_service.set_sqs_client(sqs)
        old = (settings.BATCH_BACKEND, settings.BATCH_QUEUE_URL)
        settings.BATCH_BACKEND, settings.BATCH_QUEUE_URL = "sqs", queue_url
        try:
            good = (CV_TEXT + "\nsqs-good").encode()
            result = run(batch_service.start_batch([("good.txt", good), ("copy.txt", good), ("bad.exe", b"MZ")]))
            batch_id = result["batch_id"]
            self.assertEqual(result["total"], 3)

            attrs = sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["ApproximateNumberOfMessages"])
            self.assertEqual(attrs["Attributes"]["ApproximateNumberOfMessages"], "3")
            self.assertEqual(batch_service.batch_status(batch_id)["queued"], 3)

            # One worker at a time so the duplicate is seen after the original.
            run(Worker(queue_url, concurrency=1, client=sqs).run(max_messages=3))

            status = batch_service.batch_status(batch_id)
            self.assertEqual(status.get("status"), "COMPLETE", status)
            states = sorted(f["status"] for f in status["files"])
            self.assertEqual(states, ["COMPLETED", "FAILED", "SKIPPED"])

            # Redelivery of a finished file is a no-op.
            self.assertEqual(run(batch_service.process_file(batch_id, 0)), batch_service.DONE)

            # Staged copies are removed once processed.
            for f in db.get_batch_files(batch_id):
                self.assertIsNone(get_cv_storage().checksum_sha256(f["staging_key"]))
            for f in status["files"]:
                if f["candidate_id"]:
                    db.delete_candidate(f["candidate_id"])
        finally:
            settings.BATCH_BACKEND, settings.BATCH_QUEUE_URL = old
            batch_service.set_sqs_client(None)

    @mock_aws
    def test_bulk_import_from_prefix(self):
        from backend.app.dataload import import_cvs

        sqs = boto3.client("sqs", region_name=REGION)
        queue_url = sqs.create_queue(QueueName="raas-prod-batch")["QueueUrl"]
        batch_service.set_sqs_client(sqs)
        old = (settings.BATCH_BACKEND, settings.BATCH_QUEUE_URL)
        settings.BATCH_BACKEND, settings.BATCH_QUEUE_URL = "sqs", queue_url
        storage = get_cv_storage()
        prefix = "import/test-run/"
        sources = {
            prefix + "one.txt": (CV_TEXT + "\nimport-one").encode(),
            prefix + "sub/two.TXT": (CV_TEXT + "\nimport-two").encode(),
            prefix + "dup.txt": (CV_TEXT + "\nimport-one").encode(),
            prefix + "notes.xlsx": b"PK",
            prefix + ".DS_Store": b"x",
        }
        for key, data in sources.items():
            storage.put(key, data, "application/octet-stream")
        try:
            dry = import_cvs.import_prefix(prefix, dry_run=True)
            self.assertEqual((dry["found"], dry["to_import"], dry["batches"]), (5, 3, []))
            self.assertEqual(sorted(s["reason"] for s in dry["skipped"]), ["hidden file", "unsupported format: xlsx"])

            with self.assertRaises(ValueError):
                import_cvs.import_prefix("cvs/")

            summary = import_cvs.import_prefix(prefix, batch_size=2)
            self.assertEqual([b["files"] for b in summary["batches"]], [2, 1])
            self.assertEqual(summary["queued"], 3)

            run(Worker(queue_url, concurrency=1, client=sqs).run(max_messages=3))

            report = import_cvs.build_report(prefix)
            self.assertEqual(report["result"], "PASS", report["problems"])
            self.assertEqual(report["totals"]["by_status"], {"IMPORTED": 2, "DUPLICATE": 1})
            self.assertEqual(report["totals"]["skipped_unsupported"], 2)
            self.assertIn("candidates_by_source_now", report)
            self.assertIsInstance(report["removals"], list)
            for e in report["files"]:
                if e["status"] == "IMPORTED":
                    self.assertEqual(e["stored_sha256"], e["sha256"])

            states = []
            for b in summary["batches"]:
                status = batch_service.batch_status(b["batch_id"])
                self.assertEqual(status.get("status"), "COMPLETE", status)
                states += [f["status"] for f in status["files"]]
                for f in status["files"]:
                    if f["candidate_id"]:
                        db.delete_candidate(f["candidate_id"])
            self.assertEqual(sorted(states), ["COMPLETED", "COMPLETED", "SKIPPED"])
            # With the candidates gone, the report flags the files.
            after = import_cvs.build_report(prefix)
            self.assertEqual(after["result"], "FAIL")
            self.assertEqual(after["totals"]["by_status"], {"NOT_IMPORTED": 2, "DUPLICATE": 1})
            # The uploaded originals are left in place.
            self.assertEqual(sorted(storage.list_keys(prefix)), sorted(sources))
        finally:
            for key in sources:
                storage.delete(key)
            settings.BATCH_BACKEND, settings.BATCH_QUEUE_URL = old
            batch_service.set_sqs_client(None)

    def test_retry_then_fail_after_max_attempts(self):
        rows = [{"file_index": 0, "filename": "x.txt", "file_type": "txt", "staging_key": "batch/BATCH-MISSING/0.txt", "size_bytes": 1}]
        db.create_batch("BATCH-MISSING", None, rows)  # staged object does not exist -> storage error
        outcomes = [run(batch_service.process_file("BATCH-MISSING", 0)) for _ in range(settings.WORKER_MAX_ATTEMPTS)]
        self.assertEqual(outcomes[:-1], [batch_service.RETRY] * (settings.WORKER_MAX_ATTEMPTS - 1))
        self.assertEqual(outcomes[-1], batch_service.DONE)
        status = batch_service.batch_status("BATCH-MISSING")
        self.assertEqual(status["failed"], 1)
        self.assertEqual(status.get("status"), "COMPLETE")


if __name__ == "__main__":
    unittest.main()
