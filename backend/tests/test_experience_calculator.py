import sys
import unittest
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.services.experience_calculator import ExperienceCalculator, DateParser
from backend.app.agents.evaluator_agent import CandidateEvaluatorAgent

class TestExperienceCalculator(unittest.TestCase):
    def test_date_parser(self):
        d1, approx1 = DateParser.parse_date("Jan 2022")
        self.assertEqual(d1, (2022, 1))
        self.assertFalse(approx1)

        d2, approx2 = DateParser.parse_date("03/2024")
        self.assertEqual(d2, (2024, 3))
        self.assertFalse(approx2)

        d3, approx3 = DateParser.parse_date("Present")
        self.assertEqual(d3, (2026, 8))
        self.assertFalse(approx3)

        d4, approx4 = DateParser.parse_date("2020")
        self.assertEqual(d4, (2020, 1))
        self.assertTrue(approx4)

    def test_position_duration(self):
        res = ExperienceCalculator.calculate_position_duration("Jan 2022", "Mar 2024")
        self.assertEqual(res["start_normalized"], "2022-01")
        self.assertEqual(res["end_normalized"], "2024-03")
        self.assertEqual(res["total_months"], 27)

    def test_union_experience_without_double_counting(self):
        positions = [
            {"company": "Company A", "role": "Backend Eng", "start_date": "Jan 2022", "end_date": "Dec 2023"},
            {"company": "Company B", "role": "Full Stack Eng", "start_date": "Jun 2023", "end_date": "Present"}
        ]
        res = ExperienceCalculator.calculate_total_experience_union(positions)
        self.assertTrue(res["has_overlap"])
        # Jan 2022 to Aug 2026 = 56 months (not 24 + 39 = 63 months!)
        self.assertEqual(res["total_professional_experience_months"], 56)

    def test_career_gap_detection(self):
        positions = [
            {"company": "Company A", "role": "Developer", "start_date": "Jan 2020", "end_date": "Jun 2022"},
            {"company": "Company B", "role": "Lead Dev", "start_date": "Jan 2023", "end_date": "Present"}
        ]
        gaps = ExperienceCalculator.calculate_career_gaps(positions)
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["gap_months"], 6)

    def test_technology_experience_and_insufficient_evidence(self):
        positions = [
            {
                "company": "Company A",
                "role": "React Developer",
                "start_date": "Jan 2022",
                "end_date": "Dec 2023",
                "responsibilities": ["Built UI components using React and Redux"]
            }
        ]
        skills = ["React", "Python"]
        tech_res = ExperienceCalculator.calculate_technology_experience(positions, skills)
        
        react_item = next(t for t in tech_res if t["skill"] == "React")
        self.assertEqual(react_item["confidence"], "High")
        
        python_item = next(t for t in tech_res if t["skill"] == "Python")
        self.assertEqual(python_item["calculated_experience"], "Insufficient evidence")
        self.assertEqual(python_item["confidence"], "Low")

    def test_candidate_evaluator_agent(self):
        agent = CandidateEvaluatorAgent()
        cand = {
            "candidate_id": "CAND-TEST-01",
            "full_name": "Alex Smith",
            "years_experience": 5.0,
            "skills": ["Python", "FastAPI", "React"],
            "experience": [
                {
                    "company": "Tech Corp",
                    "role": "Senior Backend Engineer",
                    "start_date": "Jan 2021",
                    "end_date": "Present",
                    "responsibilities": ["Built REST APIs with Python and FastAPI"]
                }
            ]
        }
        job = {
            "job_id": "JOB-001",
            "mandatory_skills": ["Python", "FastAPI"],
            "minimum_years_experience": 3.0
        }
        eval_report = agent.evaluate(cand, job)
        self.assertIn("overall_score", eval_report)
        self.assertIn("recommendation", eval_report)
        self.assertIn(eval_report["recommendation"], ["SHORTLIST", "STRONG MATCH", "REVIEW"])
        self.assertEqual(len(eval_report["employment_timeline"]), 1)

if __name__ == "__main__":
    unittest.main()
