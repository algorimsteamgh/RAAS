import sys
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.main import app, load_mock_dataset_internal
from backend.app.services.scoring_engine import ScoringEngine

class TestFullPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend.app.db import database as db
        db.delete_all_uploaded_candidates()
        cls.client = TestClient(app)
        load_mock_dataset_internal()
        cls.scoring_engine = ScoringEngine()

    def test_dataset_manifest_endpoint(self):
        response = self.client.get("/api/dataset/manifest")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_resumes"], 500)
        self.assertEqual(data["total_jobs"], 10)

    def test_candidates_library_list(self):
        response = self.client.get("/api/candidates")
        self.assertEqual(response.status_code, 200)
        candidates = response.json()
        self.assertIsInstance(candidates, list)
        self.assertGreater(len(candidates), 0)

    def test_deterministic_scoring(self):
        candidate = {
            "candidate_id": "CAND-TEST",
            "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
            "years_experience": 6.0,
            "domains": ["FinTech"]
        }
        job = {
            "job_id": "JOB-001",
            "title": "Senior Python Backend Engineer",
            "mandatory_skills": ["Python", "FastAPI", "PostgreSQL"],
            "preferred_skills": ["Docker", "Redis"],
            "minimum_years_experience": 5.0,
            "domain_requirements": ["FinTech"]
        }
        res = self.scoring_engine.score_candidate(candidate, job)
        self.assertEqual(res["recommendation"], "SHORTLIST")
        self.assertGreaterEqual(res["score"], 75.0)

    def test_evaluation_metrics_endpoint(self):
        response = self.client.get("/api/evaluation/metrics")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("extraction_metrics", data)
        self.assertIn("matching_metrics", data)
        em = data["extraction_metrics"]
        mm = data["matching_metrics"]
        self.assertGreaterEqual(em["skill_f1"], 0.0)
        self.assertGreaterEqual(mm["accuracy"], 0.0)
        self.assertIn("ndcg_at_10", mm)
        self.assertIn("mrr", mm)

    def test_upload_cv_endpoint(self):
        file_content = b"Candidate Name: Test Candidate\nSkills: Python, FastAPI\nExperience: Tech Corp (2022-01 - Present)"
        files = {"file": ("test_cv.txt", file_content, "text/plain")}
        response = self.client.post("/api/upload-cv?duplicate_action=replace", files=files)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("candidate_id", data)
        self.assertIn("total_professional_experience", data)

if __name__ == "__main__":
    unittest.main()
