import sys
import unittest
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.services.evidence_graph import EvidenceGraphEngine, ConfidenceLevel
from backend.app.services.matching_engine import MatchingEngine, RequirementStatus
from backend.app.services.explainable_scorer import ExplainableScorer
from backend.app.services.batch_queue import BatchQueueService

class TestEvidencePlatform(unittest.TestCase):
    def test_evidence_graph_building(self):
        cand = {
            "candidate_id": "CAND-EV-01",
            "skills": ["React", "Python"],
            "employment_history": [
                {
                    "company": "Algorims",
                    "title": "Software Development Engineer",
                    "start_date": "2026-01",
                    "end_date": "Present",
                    "responsibilities": ["Built React components and Python APIs"]
                }
            ],
            "projects": ["Built AI dashboard with Python"]
        }
        graph = EvidenceGraphEngine.build_candidate_evidence_graph(cand)
        self.assertIn("skill_graphs", graph)
        react_graph = graph["skill_graphs"]["React"]
        self.assertEqual(react_graph["confidence"], ConfidenceLevel.HIGH)
        self.assertGreater(len(react_graph["evidence_nodes"]), 0)

    def test_matching_engine_and_status(self):
        cand = {
            "candidate_id": "CAND-EV-02",
            "skills": ["Python", "FastAPI"],
            "total_professional_experience_months": 36,
            "total_professional_experience": "3 years",
            "employment_history": [
                {
                    "company": "Tech Corp",
                    "title": "Senior Engineer",
                    "start_date": "2023-01",
                    "end_date": "2026-01",
                    "responsibilities": ["Built Python APIs"]
                }
            ]
        }
        job = {
            "job_id": "JOB-EV-01",
            "minimum_years_experience": 3.0,
            "mandatory_skills": ["Python", "AWS"]
        }
        res = MatchingEngine.match_candidate_against_job(cand, job)
        analysis = res["requirement_analysis"]
        
        py_req = next(r for r in analysis if "Python" in r["requirement"])
        self.assertEqual(py_req["status"], RequirementStatus.PASS)

        aws_req = next(r for r in analysis if "AWS" in r["requirement"])
        self.assertEqual(aws_req["status"], RequirementStatus.FAIL)

    def test_explainable_scorer_hero_features(self):
        cand = {
            "candidate_id": "CAND-HERO-01",
            "skills": ["React", "Node.js"],
            "years_experience": 5.0,
            "total_professional_experience_months": 44,
            "total_professional_experience": "3 years 8 months",
            "internship_experience": "6 months",
            "total_experience_including_internships": "4 years 2 months",
            "current_company": "Algorims",
            "current_title": "Software Engineer",
            "current_employment_start_date": "2026-01",
            "notice_period": "30 days",
            "employment_history": [
                {
                    "company": "Algorims",
                    "title": "Software Engineer",
                    "start_date": "2026-01",
                    "end_date": "Present",
                    "responsibilities": ["Built React components and Node.js backend"]
                }
            ],
            "education": ["B.Tech CS"]
        }
        job = {
            "minimum_years_experience": 3.0,
            "mandatory_skills": ["React", "Node.js", "AWS"]
        }
        score_res = ExplainableScorer.calculate_explainable_score(cand, job)
        
        self.assertIn("overall_score", score_res)
        self.assertIn("recommendation", score_res)
        self.assertIn("why_this_candidate", score_res)
        self.assertIn("what_is_missing", score_res)
        self.assertIn("experience_truth", score_res)
        
        truth = score_res["experience_truth"]
        self.assertEqual(truth["calculated_professional_experience"], "3 years 8 months")
        self.assertEqual(truth["current_company"], "Algorims")

    def test_batch_queue_service(self):
        service = BatchQueueService()
        files = [{"filename": "res1.pdf"}, {"filename": "res2.pdf"}]
        batch = service.create_batch_job("batch_01", files)
        self.assertEqual(batch["total"], 2)
        self.assertEqual(batch["status"], "QUEUED")

if __name__ == "__main__":
    unittest.main()
