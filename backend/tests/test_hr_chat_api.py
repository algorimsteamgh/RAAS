import sys
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.main import app
from backend.app.db import database as db
from backend.app.agents.hr_chat_agent import HRChatAgent

class TestHRChatAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        
        # Ensure at least one test candidate exists
        self.candidate_id = "TEST-CAND-CHAT-001"
        test_cand = {
            "candidate_id": self.candidate_id,
            "full_name": "Jordan Lee",
            "email": "jordan.lee@example.com",
            "phone": "+1 555-0199",
            "location": "San Francisco, CA",
            "current_title": "Senior Staff Python Engineer",
            "years_experience": 8.5,
            "roles": ["Senior Staff Python Engineer", "Backend Developer"],
            "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes", "Redis", "Distributed Systems"],
            "work_experience": [
                {
                    "title": "Senior Staff Python Engineer",
                    "company": "ScaleCloud Inc",
                    "start_date": "2021-01",
                    "end_date": "Present",
                    "duration_years": 3.5,
                    "description": "Led backend architecture using FastAPI, PostgreSQL, and Docker."
                },
                {
                    "title": "Backend Developer",
                    "company": "DataPulse LLC",
                    "start_date": "2016-01",
                    "end_date": "2020-12",
                    "duration_years": 5.0,
                    "description": "Maintained distributed microservices and Redis caches."
                }
            ],
            "career_gaps": [],
            "education": [{"degree": "B.S. in Computer Science", "institution": "UC Berkeley", "year": "2015"}]
        }
        db.save_candidate_record(test_cand, source="TEST", status="COMPLETED")
        
        # Also ensure a test job exists
        self.job_id = "TEST-JOB-CHAT-001"
        test_job = {
            "job_id": self.job_id,
            "title": "Lead Backend Engineer",
            "department": "Engineering",
            "minimum_years_experience": 6.0,
            "required_skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
            "preferred_skills": ["Kubernetes", "Redis"],
            "description": "Looking for an experienced Lead Backend Engineer."
        }
        db.save_job(test_job)
        
        # Clear chat history for clean slate
        db.clear_chat_history(self.candidate_id)

    def tearDown(self):
        db.clear_chat_history(self.candidate_id)
        db.delete_candidate(self.candidate_id)

    def test_hr_chat_agent_fallback_direct(self):
        agent = HRChatAgent()
        cand_data = db.get_candidate_by_id(self.candidate_id)
        job_data = db.get_job_by_id(self.job_id)
        
        # Test strengths query
        res = agent._heuristic_fallback_response("What are their key strengths?", cand_data, job_data, None)
        self.assertIn("Jordan Lee", res)
        self.assertTrue("Python" in res or "FastAPI" in res or "Strengths" in res)

        # Test email draft query
        res_email = agent._heuristic_fallback_response("Draft a screening invitation email", cand_data, job_data, None)
        self.assertIn("Subject:", res_email)
        self.assertIn("Jordan", res_email)

        # Test questions query
        res_q = agent._heuristic_fallback_response("Suggest interview questions", cand_data, job_data, None)
        self.assertTrue("Interview" in res_q or "Questions" in res_q or "1." in res_q)

    def test_chat_endpoint_multi_turn(self):
        # 1. Send first message
        payload = {
            "message": "Can you summarize Jordan's background and suitability?",
            "job_id": self.job_id,
            "save_history": True
        }
        resp = self.client.post(f"/api/candidates/{self.candidate_id}/chat", json=payload)
        self.assertEqual(resp.status_code, 200, f"Chat failed: {resp.text}")
        data = resp.json()
        self.assertEqual(data["candidate_id"], self.candidate_id)
        self.assertTrue(len(data["reply"]) > 20)
        self.assertIsInstance(data["suggested_followups"], list)
        self.assertTrue(len(data["suggested_followups"]) > 0)

        # 2. Check chat history
        hist_resp = self.client.get(f"/api/candidates/{self.candidate_id}/chat-history")
        self.assertEqual(hist_resp.status_code, 200)
        hist_data = hist_resp.json()
        self.assertEqual(hist_data["total"], 2)  # 1 user + 1 assistant
        self.assertEqual(hist_data["messages"][0]["role"], "user")
        self.assertEqual(hist_data["messages"][1]["role"], "assistant")

        # 3. Send follow-up message
        payload2 = {
            "message": "Draft a phone screen invitation email to Jordan",
            "job_id": self.job_id,
            "save_history": True
        }
        resp2 = self.client.post(f"/api/candidates/{self.candidate_id}/chat", json=payload2)
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertIn("Subject:", data2["reply"])

        # 4. Check updated history count
        hist_resp2 = self.client.get(f"/api/candidates/{self.candidate_id}/chat-history")
        self.assertEqual(hist_resp2.json()["total"], 4)

        # 5. Clear history
        del_resp = self.client.delete(f"/api/candidates/{self.candidate_id}/chat-history")
        self.assertEqual(del_resp.status_code, 200)
        self.assertEqual(del_resp.json()["deleted_count"], 4)

        # 6. Verify cleared history is now 0
        hist_resp3 = self.client.get(f"/api/candidates/{self.candidate_id}/chat-history")
        self.assertEqual(hist_resp3.json()["total"], 0)

    def test_chat_nonexistent_candidate(self):
        resp = self.client.post("/api/candidates/NON-EXISTENT-ID/chat", json={"message": "Hello"})
        self.assertEqual(resp.status_code, 404)

if __name__ == "__main__":
    unittest.main()
