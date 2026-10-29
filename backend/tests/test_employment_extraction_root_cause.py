import asyncio
from backend.app.services.experience_calculator import DateNormalizer, ExperienceCalculator
from backend.app.services.document_layout import DocumentLayoutEngine
from backend.app.agents.cv_agent import CVExtractionAgent
from backend.app.agents.evaluator_agent import CandidateEvaluatorAgent

GROUND_TRUTH_CV_TEXT = """
Alex Morgan
Software Development Engineer
San Francisco, CA, USA
alex.morgan@example.com | +1 555-019-2834

Professional Summary
Software Development Engineer with experience designing and building scalable full-stack applications and AI-powered solutions.
Hands-on experience building Generative AI applications using Large Language Models (LLMs), Retrieval-Augmented
Generation (RAG), Model Context Protocol (MCP), AI agents, vector databases, and semantic search.

Technical Skills
Languages: Java, Python, TypeScript, JavaScript, SQL
Frontend: React.js, Redux Toolkit, HTML5, CSS3
Backend: Node.js, Express.js, Spring Boot, REST APIs, WebSockets
Databases: PostgreSQL, Firebase
Cloud & DevOps: AWS, Docker, Git, GitHub Actions, Linux, CI/CD
AI: LLMs, Claude API, RAG, AI Agents, Prompt Engineering, MCP, Vector Databases

Professional Experience
Software Development Engineer & AI Engineer Jan 2026 – Present
Algorims
• Designed and developed scalable full-stack applications using React, TypeScript, Node.js and PostgreSQL.
• Implemented Retrieval-Augmented Generation (RAG) using vector databases and semantic search.
• Built Model Context Protocol (MCP) integrations connecting AI systems with enterprise tools.
Software Developer Intern Jul 2025 – Dec 2025
Algorims
• Developed reusable React components and enterprise dashboards.
• Built REST APIs using Node.js and PostgreSQL.
Software Developer Trainee Apr 2025 – Jun 2025
Algorims
• Developed backend services using Node.js.
• Documented APIs with Swagger.
Associate II – Operations Jul 2024 – Feb 2025
Mervice Infotech Pvt. Ltd.
• Automated reporting workflows and operational dashboards.
Java Developer Intern Oct 2023 – Nov 2023
ASAR IT Technologies
• Developed Java applications using Firebase and assisted with debugging.
Python Developer Intern Sep 2022 – Oct 2022
Amara Raja Power Systems
• Built a Battery Management System GUI using Python Tkinter.

Education
Bachelor of Technology in Electronics and Communication Engineering 2020–2024
Sri Venkatesa Perumal College of Engineering and Technology
"""

def test_date_normalizer_formats_and_edge_cases():
    # 1. Standard Month Year
    s_ym, e_ym, is_curr, valid = DateNormalizer.parse_date_range_string("Jan 2026 – Present")
    assert valid is True
    assert s_ym == "2026-01"
    assert e_ym is None
    assert is_curr is True

    # 2. Full Month Names
    s_ym, e_ym, is_curr, valid = DateNormalizer.parse_date_range_string("January 2026 – Current")
    assert valid is True
    assert s_ym == "2026-01"
    assert is_curr is True

    # 3. Abbreviated Historical Range
    s_ym, e_ym, is_curr, valid = DateNormalizer.parse_date_range_string("Jul 2025 – Dec 2025")
    assert valid is True
    assert s_ym == "2025-07"
    assert e_ym == "2025-12"
    assert is_curr is False

    # 4. ISO Numeric Range
    s_ym, e_ym, is_curr, valid = DateNormalizer.parse_date_range_string("2025-07 – 2025-12")
    assert valid is True
    assert s_ym == "2025-07"
    assert e_ym == "2025-12"

    # 5. Slash Numeric Range
    s_ym, e_ym, is_curr, valid = DateNormalizer.parse_date_range_string("07/2025 – 12/2025")
    assert valid is True
    assert s_ym == "2025-07"
    assert e_ym == "2025-12"

    # 6. Year Only Range
    s_ym, e_ym, is_curr, valid = DateNormalizer.parse_date_range_string("2020–2024")
    assert valid is True
    assert s_ym == "2020-01"
    assert e_ym == "2024-01"

    # 7. Non-Date String (Must Reject cleanly)
    s_ym, e_ym, is_curr, valid = DateNormalizer.parse_date_range_string("RAG")
    assert valid is False
    assert s_ym is None

    # 8. Start Date after End Date check in duration
    dur_info = ExperienceCalculator.calculate_position_duration("2026-05", "2025-01", is_current=False)
    assert dur_info["is_valid"] is False

def test_ground_truth_employment_extraction():
    positions = DocumentLayoutEngine.extract_structured_employment_records(GROUND_TRUTH_CV_TEXT)
    
    # 1. Exactly 6 positions
    assert len(positions) == 6, f"Expected 6 positions, got {len(positions)}"

    # 2. No fake positions called "Retrieval" or "Implemented Retrieval"
    for p in positions:
        assert "retrieval" not in p["company"].lower()
        assert "retrieval" not in p["title"].lower()
        assert "rag" not in p["company"].lower()
        assert "rag" not in p["title"].lower()

    # 3. Check exact company and role records
    assert positions[0]["title"] == "Software Development Engineer & AI Engineer"
    assert positions[0]["company"] == "Algorims"
    assert positions[0]["start_date"] == "2026-01"
    assert positions[0]["end_date"] is None
    assert positions[0]["is_current"] is True

    assert positions[1]["title"] == "Software Developer Intern"
    assert positions[1]["company"] == "Algorims"
    assert positions[1]["start_date"] == "2025-07"
    assert positions[1]["end_date"] == "2025-12"
    assert positions[1]["is_current"] is False

    assert positions[2]["title"] == "Software Developer Trainee"
    assert positions[2]["company"] == "Algorims"
    assert positions[2]["start_date"] == "2025-04"
    assert positions[2]["end_date"] == "2025-06"

    assert positions[3]["title"] == "Associate II – Operations"
    assert positions[3]["company"] == "Mervice Infotech Pvt. Ltd."
    assert positions[3]["start_date"] == "2024-07"
    assert positions[3]["end_date"] == "2025-02"

    assert positions[4]["title"] == "Java Developer Intern"
    assert positions[4]["company"] == "ASAR IT Technologies"
    assert positions[4]["start_date"] == "2023-10"
    assert positions[4]["end_date"] == "2023-11"

    assert positions[5]["title"] == "Python Developer Intern"
    assert positions[5]["company"] == "Amara Raja Power Systems"
    assert positions[5]["start_date"] == "2022-09"
    assert positions[5]["end_date"] == "2022-10"

    # 4. ExperienceCalculator total
    calc_res = ExperienceCalculator.calculate_total_experience_union(positions)
    assert calc_res["total_professional_experience_months"] == 16  # Jan 2026-Aug 2026 (8 mos) + Apr 2025-Jun 2025 (3 mos) + Jul 2024-Feb 2025 (8 mos) - overlaps = 16 mos
    assert calc_res["internship_experience_months"] == 13
    assert calc_res["has_overlap"] is False

def test_claimed_vs_calculated_experience_handling():
    # 1. When not explicitly stated in summary
    claimed, status = DocumentLayoutEngine.extract_claimed_years_experience(GROUND_TRUTH_CV_TEXT)
    assert claimed is None
    assert status == "NOT_STATED"

    # 2. When explicitly stated in summary e.g. "Software Engineer with 4.5+ years of experience"
    sample_with_claim = "Software Engineer with 4.5+ years of experience in Python."
    claimed2, status2 = DocumentLayoutEngine.extract_claimed_years_experience(sample_with_claim)
    assert claimed2 == 4.5
    assert status2 == "EXPLICITLY_CLAIMED"

async def test_full_agent_extraction_and_evaluator_trace():
    agent = CVExtractionAgent()
    agent.client.timeout = 0.05

    candidate = await agent.extract_candidate(GROUND_TRUTH_CV_TEXT, candidate_id="TEST-GT-001")
    
    assert candidate.candidate_id == "TEST-GT-001"
    assert candidate.total_professional_experience_months == 16
    assert candidate.total_professional_experience == "1 year 4 months"
    assert len(candidate.employment_history) == 6
    assert candidate.current_company == "Algorims"
    assert candidate.current_title == "Software Development Engineer & AI Engineer"
    assert candidate.candidate_claim_status == "NOT_STATED"

    # Evaluator Agent
    evaluator = CandidateEvaluatorAgent()
    job = {
        "job_id": "JOB-SDE",
        "title": "Software Development Engineer",
        "minimum_years_experience": 1.0,
        "mandatory_skills": ["Python", "Java", "React", "SQL"]
    }
    report = evaluator.evaluate(candidate.model_dump(), job_description=job)
    
    assert report["candidate_id"] == "TEST-GT-001"
    assert report["total_professional_experience"] == "1 year 4 months"
    assert report["claimed_experience"] == "Not explicitly claimed"
    assert report["status"] in ["PASS", "PARTIAL"]
    assert report["calibrated_confidence"] >= 0.70

if __name__ == "__main__":
    test_date_normalizer_formats_and_edge_cases()
    test_ground_truth_employment_extraction()
    test_claimed_vs_calculated_experience_handling()
    asyncio.run(test_full_agent_extraction_and_evaluator_trace())
    print("ALL ROOT-CAUSE REGRESSION TESTS PASSED 100% SUCCESSFULLY!")
