"""
Interview Verification Engine
Generates recruiter verification questions for VERIFY/MISSING/UNCERTAIN evidence items.
Questions are deterministic templates — not LLM-generated — linked to specific requirement gaps.
"""
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Deterministic question templates keyed by gap category
QUESTION_TEMPLATES = {
    "experience_duration": [
        "Can you walk me through your experience with {skill}? Specifically, which projects or roles involved it, and for how long?",
        "Describe the most complex {skill} work you've done in a production environment. When did you do this work?",
    ],
    "experience_gap": [
        "Your resume shows a gap between {gap_start} and {gap_end}. Could you share what you were doing during that period?",
    ],
    "timeline_discrepancy": [
        "Your resume indicates approximately {claimed} of experience, but the employment timeline we calculated shows {calculated}. Can you help us understand this difference?",
    ],
    "skill_verify": [
        "You mention {skill} in your resume. Can you describe the specific {skill} services or tools you've used in production and the time period you worked with them?",
        "Tell us about a challenging problem you solved using {skill}. What was the context and when did this happen?",
    ],
    "skill_missing": [
        "This role requires {skill}. Do you have experience with {skill}? If so, could you describe a project where you used it?",
    ],
    "leadership": [
        "Tell us about a project where you were responsible for technical direction or coordinating other engineers.",
        "Have you mentored junior developers or led a team? Describe the scale and duration.",
    ],
    "overlap": [
        "We noticed overlapping employment periods between {company_a} and {company_b} ({overlap_period}). Could you clarify whether these were concurrent positions?",
    ],
    "education": [
        "This role prefers {requirement}. Could you describe any relevant education, certifications, or equivalent experience?",
    ],
    "domain": [
        "This position requires experience in the {domain} domain. Can you describe your relevant experience in this area?",
    ],
}


class InterviewEngine:
    @staticmethod
    def generate_verification_questions(
        candidate_data: Dict[str, Any],
        job_data: Dict[str, Any],
        requirement_analysis: List[Dict[str, Any]],
        experience_truth: Optional[Dict[str, Any]] = None,
        career_gaps: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate interview verification questions based on evidence gaps.
        Returns a list of { category, requirement, status, reason, question }.
        """
        questions = []

        # 1. Questions for VERIFY/MISSING/UNKNOWN/PARTIAL requirements
        for req in requirement_analysis:
            status = req.get("status", "PASS")
            if status == "PASS":
                continue

            req_name = req.get("requirement", "").replace("Required Skill: ", "").replace("Preferred Skill: ", "")
            category = req.get("category", "REQUIRED_SKILL")
            evidence = req.get("evidence_summary", "")

            if status in ("UNKNOWN", "PARTIAL"):
                templates = QUESTION_TEMPLATES.get("skill_verify", [])
                reason = f"{req_name} appears in the resume but lacks sufficient employment-period evidence."
            elif status == "FAIL":
                if "PREFERRED" in category:
                    templates = QUESTION_TEMPLATES.get("skill_missing", [])
                    reason = f"Preferred skill {req_name} was not found in the resume."
                else:
                    templates = QUESTION_TEMPLATES.get("skill_missing", [])
                    reason = f"Required skill {req_name} was not found in the resume."
            else:
                templates = QUESTION_TEMPLATES.get("skill_verify", [])
                reason = evidence

            if templates:
                q = templates[0].format(skill=req_name)
                questions.append({
                    "category": "skill_verification",
                    "requirement": req_name,
                    "status": status,
                    "reason": reason,
                    "question": q,
                    "priority": "HIGH" if "REQUIRED" in category else "MEDIUM",
                })

        # 2. Timeline discrepancy questions
        if experience_truth:
            discrepancy = experience_truth.get("discrepancy_note", "None")
            if discrepancy and discrepancy != "None":
                claimed = experience_truth.get("claimed_experience", "")
                calculated = experience_truth.get("calculated_professional_experience", "")
                templates = QUESTION_TEMPLATES.get("timeline_discrepancy", [])
                if templates:
                    q = templates[0].format(claimed=claimed, calculated=calculated)
                    questions.append({
                        "category": "timeline_verification",
                        "requirement": "Experience Duration",
                        "status": "VERIFY",
                        "reason": discrepancy,
                        "question": q,
                        "priority": "HIGH",
                    })

        # 3. Career gap questions
        if career_gaps:
            for gap in career_gaps:
                between = gap.get("between", "")
                duration = gap.get("duration_formatted", "")
                templates = QUESTION_TEMPLATES.get("experience_gap", [])
                if templates and between:
                    parts = between.split(" and ")
                    gap_start = parts[0].strip() if len(parts) > 0 else "unknown"
                    gap_end = parts[1].strip() if len(parts) > 1 else "unknown"
                    q = templates[0].format(gap_start=gap_start, gap_end=gap_end)
                    questions.append({
                        "category": "career_gap",
                        "requirement": f"Career Gap ({duration})",
                        "status": "VERIFY",
                        "reason": f"Unexplained career gap of {duration} detected.",
                        "question": q,
                        "priority": "MEDIUM",
                    })

        # 4. Leadership questions (if job requires seniority)
        seniority = job_data.get("seniority", "").lower()
        if any(level in seniority for level in ["senior", "lead", "principal", "staff", "manager", "director"]):
            has_leadership_evidence = any(
                "lead" in str(req.get("requirement", "")).lower() or "leadership" in str(req.get("requirement", "")).lower()
                for req in requirement_analysis
                if req.get("status") == "PASS"
            )
            if not has_leadership_evidence:
                templates = QUESTION_TEMPLATES.get("leadership", [])
                if templates:
                    questions.append({
                        "category": "leadership_verification",
                        "requirement": "Leadership / Seniority",
                        "status": "VERIFY",
                        "reason": "Role requires senior-level leadership evidence, which was not strongly demonstrated in the resume.",
                        "question": templates[0],
                        "priority": "MEDIUM",
                    })

        # Sort by priority
        priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        questions.sort(key=lambda q: priority_order.get(q.get("priority", "LOW"), 2))

        return questions
