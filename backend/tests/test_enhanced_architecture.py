import asyncio
from backend.app.agents.cv_agent import CVExtractionAgent, SAFE_CONTEXT_TOKEN_LIMIT
from backend.app.agents.evaluator_agent import CandidateEvaluatorAgent
from backend.app.services.evidence_verifier import EvidenceVerifier
from backend.app.schemas.candidate import VerificationStatus

SAMPLE_SHORT_CV = """
John Doe
Senior Full Stack Engineer
Tirupati, Andhra Pradesh, India
Email: john.doe@example.com | Phone: +91 9876543210
Notice Period: 30 days

SUMMARY:
Results-driven Senior Full Stack Engineer with 5+ years of experience building high-scale Python, FastAPI, and React applications.

WORK EXPERIENCE:
Senior Software Engineer - TechCorp India (2022-01 to Present)
- Designed and deployed RESTful microservices using Python, FastAPI, and PostgreSQL.
- Architected responsive frontend applications in React and TypeScript.
- Implemented Docker containerization and CI/CD automation pipelines.

Software Developer - Innovate Labs (2019-06 to 2021-12)
- Built backend APIs with Python and Flask.
- Collaborated on database schema design with PostgreSQL.

EDUCATION:
Bachelor of Technology in Computer Science - IIT Madras (2015 to 2019)

SKILLS:
Python, FastAPI, React, TypeScript, PostgreSQL, Docker, Git
"""

def test_evidence_verifier_exact_and_normalized():
    # 1. Locate snippet
    snippet = "RESTful microservices using Python, FastAPI, and PostgreSQL"
    found, start, end = EvidenceVerifier.locate_snippet_in_text(snippet, SAMPLE_SHORT_CV)
    assert found is True
    assert start is not None and end is not None

    # 2. Non-existent snippet
    found_bad, _, _ = EvidenceVerifier.locate_snippet_in_text("Expert in Ruby on Rails and Kubernetes 1.28", SAMPLE_SHORT_CV)
    assert found_bad is False

def test_evidence_grounding_and_hallucination_detection():
    candidate_data = {
        "candidate_id": "TEST-001",
        "skills": ["Python", "FastAPI", "React", "RustLangHallucination"],
        "employment_history": [
            {"company": "TechCorp India", "title": "Senior Software Engineer", "start_date": "2022-01", "end_date": "Present"}
        ],
        "evidence": [
            {"attribute": "skills:Python", "source_text": "RESTful microservices using Python", "source_section": "Experience"}
        ]
    }

    grounded = EvidenceVerifier.verify_and_ground_candidate(candidate_data, SAMPLE_SHORT_CV)
    
    # "RustLangHallucination" should be stripped from grounded skills and flagged in ambiguities
    assert "Python" in grounded["skills"]
    assert "RustLangHallucination" not in grounded["skills"]
    
    ambiguities = grounded["potential_ambiguities"]
    hallucination_flags = [a for a in ambiguities if a["category"] == "HALLUCINATED_SKILL"]
    assert len(hallucination_flags) > 0
    assert "RustLangHallucination" in hallucination_flags[0]["description"]

async def test_full_document_extraction_and_evaluation():
    agent = CVExtractionAgent()
    agent.client.timeout = 0.05
    
    # Run extraction (will use heuristic fallback if Ollama not running)
    candidate = await agent.extract_candidate(SAMPLE_SHORT_CV, candidate_id="TEST-SHORT-001")
    
    assert candidate.candidate_id == "TEST-SHORT-001"
    assert candidate.total_professional_experience_months > 0
    assert len(candidate.skills) > 0
    assert candidate.extraction_method == "FULL_DOCUMENT"
    
    # Evaluate candidate against a Job Description
    evaluator = CandidateEvaluatorAgent()
    job_desc = {
        "job_id": "JOB-TEST-1",
        "title": "Senior Python Engineer",
        "minimum_years_experience": 3.0,
        "mandatory_skills": ["Python", "FastAPI"],
        "preferred_skills": ["Docker", "PostgreSQL"]
    }
    
    report = evaluator.evaluate(candidate.model_dump(), job_description=job_desc)
    
    assert report["candidate_id"] == "TEST-SHORT-001"
    assert report["status"] in ["PASS", "PARTIAL"]
    assert 0.0 <= report["calibrated_confidence"] <= 1.0
    assert len(report["matched_requirements"]) > 0
    assert report["total_professional_experience"] != "0 months"
    assert "qualitative_reasoning" in report

async def test_sequential_chunking_fallback_for_long_cv():
    agent = CVExtractionAgent()
    agent.client.timeout = 0.05
    
    # Create an artificially long CV by repeating content with distinct sections
    long_cv_parts = [
        SAMPLE_SHORT_CV,
        "\n\nPROJECTS & PATENTS:\n" + ("Built large scale distributed system with Python, FastAPI, React, and PostgreSQL.\n" * 150),
        "\n\nADDITIONAL EXPERIENCE:\n" + ("Software Consultant - Global Enterprise (2017-01 to 2019-05)\nDelivered analytics pipelines.\n" * 120),
        "\n\nPUBLICATIONS & TALKS:\n" + ("Speaker at PyCon on High Performance FastAPI Architecture.\n" * 100)
    ]
    long_cv = "".join(long_cv_parts)
    
    est_tokens = agent.estimate_token_count(long_cv)
    assert est_tokens > SAFE_CONTEXT_TOKEN_LIMIT
    
    candidate = await agent.extract_candidate(long_cv, candidate_id="TEST-LONG-001")
    
    assert candidate.candidate_id == "TEST-LONG-001"
    assert candidate.extraction_method == "SEQUENTIAL_CHUNKS"
    assert len(candidate.skills) > 0
    assert candidate.total_professional_experience_months > 0

if __name__ == "__main__":
    test_evidence_verifier_exact_and_normalized()
    test_evidence_grounding_and_hallucination_detection()
    asyncio.run(test_full_document_extraction_and_evaluation())
    asyncio.run(test_sequential_chunking_fallback_for_long_cv())
    print("All architecture tests PASSED successfully!")
