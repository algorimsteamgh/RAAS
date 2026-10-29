import sys
import unittest
import asyncio
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.agents.cv_agent import CVExtractionAgent
from backend.app.services.experience_calculator import ExperienceCalculator

class TestStructuredParser(unittest.TestCase):
    def test_location_extraction_and_rules(self):
        cv_text = """
        Candidate Name: Rajesh Sharma
        Location: Tirupati, Andhra Pradesh, India
        Email: rajesh.sharma@example.com
        Phone: +919876543210
        Notice Period: 30 days

        PROFESSIONAL EXPERIENCE:
        Algorims — Software Development Engineer (2026-01 - Present)
        Developed AI services.

        Algorims — Software Developer Intern (2025-07 - 2025-12)
        Interned on backend features.
        """
        agent = CVExtractionAgent()
        result = asyncio.run(agent.extract_candidate(cv_text, "CAND-RULES-01"))
        
        self.assertEqual(result.name, "Rajesh Sharma")
        self.assertIn("Tirupati", result.location)
        self.assertEqual(result.notice_period, "30 days")
        self.assertEqual(result.current_company, "Algorims")
        
        # Internship separation
        self.assertGreater(result.total_professional_experience_months, 0)
        self.assertEqual(result.internship_experience_months, 6)
        self.assertEqual(result.internship_experience, "6 months")

    def test_overlapping_employment_union(self):
        positions = [
            {"company": "Company A", "role": "Engineer", "start_date": "2024-01", "end_date": "2025-12"},
            {"company": "Company B", "role": "Lead Engineer", "start_date": "2025-06", "end_date": "Present"}
        ]
        calc = ExperienceCalculator.calculate_total_experience_union(positions)
        # Jan 2024 to Aug 2026 = 32 months union (not 24 + 15 = 39 months)
        self.assertEqual(calc["total_professional_experience_months"], 32)
        self.assertTrue(calc["has_overlap"])

    def test_notice_period_not_specified_rule(self):
        cv_text = """
        Candidate Name: Ananya Patel
        Email: ananya@example.com
        
        EXPERIENCE:
        Tech Systems — Developer (2023-01 - Present)
        """
        agent = CVExtractionAgent()
        result = asyncio.run(agent.extract_candidate(cv_text, "CAND-RULES-02"))
        self.assertEqual(result.notice_period, "Not specified")

if __name__ == "__main__":
    unittest.main()
