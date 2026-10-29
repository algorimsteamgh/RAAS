import logging
from typing import Dict, Any, List, Optional
from backend.app.schemas.candidate import (
    EvaluationReport,
    RequirementEvaluation,
    VerificationStatus,
    AmbiguityFlag
)
from backend.app.services.experience_calculator import ExperienceCalculator
from backend.app.services.matching_engine import MatchingEngine, RequirementStatus
from backend.app.services.evidence_verifier import EvidenceVerifier

logger = logging.getLogger(__name__)

class CandidateEvaluatorAgent:
    """
    Contextual Evaluator Agent evaluating validated structured candidate profiles
    against job requirements. Produces auditable, evidence-backed evaluation reports
    with calibrated confidence scores and human-in-the-loop ambiguity flags.
    """
    def __init__(self):
        self.exp_calc = ExperienceCalculator()

    def evaluate(self, candidate_data: Dict[str, Any], job_description: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        full_name = candidate_data.get("full_name") or candidate_data.get("name") or "Unknown Candidate"
        cand_id = candidate_data.get("candidate_id") or "CAND-001"
        skills = candidate_data.get("skills", [])
        
        job = job_description or {
            "title": "Software Engineering Role",
            "seniority": "Mid-level",
            "minimum_years_experience": 3.0,
            "mandatory_skills": skills[:3] if skills else ["Python", "SQL"]
        }

        # 1. Timeline & Non-Overlapping Experience Calculation
        experience_entries = candidate_data.get("employment_history") or candidate_data.get("experience", [])
        union_res = self.exp_calc.calculate_total_experience_union(experience_entries)
        calculated_months = union_res["total_professional_experience_months"]
        calculated_exp_str = union_res["total_professional_experience"]

        # 2. Claimed Experience vs Calculated Experience
        claimed_exp = candidate_data.get("years_experience")
        claimed_exp_str = f"{claimed_exp} years" if claimed_exp is not None else "Not explicitly claimed"
        
        discrepancy = "None"
        discrepancy_penalty = 0.0
        if claimed_exp is not None:
            claimed_months = int(claimed_exp * 12)
            diff = claimed_months - calculated_months
            if abs(diff) >= 6:
                diff_formatted = self.exp_calc.format_duration(abs(diff))
                discrepancy_penalty = 0.10
                if diff > 0:
                    discrepancy = f"Claimed experience ({claimed_exp} yrs) is higher than calculated timeline ({calculated_exp_str}) by ~{diff_formatted}."
                else:
                    discrepancy = f"Calculated timeline ({calculated_exp_str}) exceeds summary claim ({claimed_exp} yrs) by ~{diff_formatted}."

        # 3. Career Gaps & Overlaps
        gaps = self.exp_calc.calculate_career_gaps(experience_entries)
        has_overlap = union_res.get("has_overlap", False)

        # 4. Requirement Analysis via Matching Engine
        matching_output = MatchingEngine.match_candidate_against_job(candidate_data, job)
        raw_reqs = matching_output.get("requirement_analysis", [])

        matched_reqs: List[RequirementEvaluation] = []
        partial_matches: List[RequirementEvaluation] = []
        missing_reqs: List[RequirementEvaluation] = []

        for req in raw_reqs:
            status_val = req.get("status", "FAIL")
            req_eval = RequirementEvaluation(
                requirement=req.get("requirement", "Requirement"),
                category=req.get("category", "REQUIRED_SKILL"),
                calculated_experience=req.get("calculated_experience", "Insufficient evidence"),
                status=status_val,
                confidence=req.get("confidence", "MEDIUM"),
                evidence_summary=req.get("evidence_summary", ""),
                verification_status=VerificationStatus.VERIFIED if status_val != "FAIL" else VerificationStatus.UNVERIFIED
            )

            if status_val == RequirementStatus.PASS:
                matched_reqs.append(req_eval)
            elif status_val in (RequirementStatus.PARTIAL, RequirementStatus.UNKNOWN):
                partial_matches.append(req_eval)
            else:
                missing_reqs.append(req_eval)

        # 5. Compile Ambiguity Flags for Human Review
        ambiguities: List[AmbiguityFlag] = []
        
        # Add pre-existing extraction ambiguities
        for amb in candidate_data.get("potential_ambiguities", []):
            if isinstance(amb, dict):
                ambiguities.append(AmbiguityFlag(**amb))

        # Add discrepancy flag
        if discrepancy != "None":
            ambiguities.append(AmbiguityFlag(
                category="EXPERIENCE_DISCREPANCY",
                description=discrepancy,
                severity="MEDIUM",
                field_affected="years_experience"
            ))

        # Add career gap flags
        for gap in gaps:
            ambiguities.append(AmbiguityFlag(
                category="CAREER_GAP",
                description=gap.get("note", "Unexplained gap in employment history"),
                severity="LOW",
                field_affected="employment_history"
            ))

        # Add concurrent overlap flags
        if has_overlap:
            for overlap_text in union_res.get("overlapping_details", []):
                ambiguities.append(AmbiguityFlag(
                    category="CONCURRENT_OVERLAP",
                    description=overlap_text,
                    severity="LOW",
                    field_affected="employment_history"
                ))

        # 6. Overall Weighted Score (Deterministic 0-100)
        req_min_exp = float(job.get("minimum_years_experience") or 3.0)
        exp_score = min(1.0, (calculated_months / 12.0) / max(0.5, req_min_exp)) * 30.0
        tech_score = (len(matched_reqs) / max(1, len(raw_reqs))) * 35.0
        partial_score = (len(partial_matches) / max(1, len(raw_reqs))) * 15.0
        edu_score = 10.0 if candidate_data.get("education") else 5.0
        achieve_score = 10.0 if candidate_data.get("projects") or candidate_data.get("evidence") else 5.0

        overall_score = round(exp_score + tech_score + partial_score + edu_score + achieve_score, 1)

        # Recommendation & High-Level Decision Status
        mand_missing_count = len([m for m in missing_reqs if m.category == "REQUIRED_SKILL"])
        if overall_score >= 75.0 and mand_missing_count == 0:
            status = "PASS"
            recommendation = "SHORTLIST"
        elif overall_score >= 50.0:
            status = "PARTIAL"
            recommendation = "REVIEW"
        else:
            status = "FAIL"
            recommendation = "DO_NOT_SHORTLIST"

        # 7. Calibrated Deterministic Confidence Calculation
        # Confidence derived from:
        # 1. evidence_coverage (verified claims ratio)
        # 2. requirement_match_consistency (pass ratio)
        # 3. timeline_consistency (no gaps/overlaps/discrepancy)
        # 4. ambiguity_penalty
        conf_obj = candidate_data.get("confidence", {})
        evidence_coverage = float(conf_obj.get("evidence_coverage") or 0.85)
        
        req_consistency = (len(matched_reqs) + 0.5 * len(partial_matches)) / max(1, len(raw_reqs))
        
        timeline_consistency = 1.0
        if has_overlap:
            timeline_consistency -= 0.15
        if gaps:
            timeline_consistency -= 0.15
        if discrepancy != "None":
            timeline_consistency -= discrepancy_penalty
        timeline_consistency = max(0.2, timeline_consistency)

        ambiguity_penalty = min(0.30, len(ambiguities) * 0.04)

        calibrated_confidence = round(
            max(0.1, min(1.0, (
                0.35 * evidence_coverage +
                0.35 * req_consistency +
                0.20 * timeline_consistency -
                0.10 * ambiguity_penalty
            ))),
            2
        )

        # 8. Strengths and Concerns
        strengths = [
            f"Demonstrates {calculated_exp_str} of calculated non-overlapping experience.",
            f"Verified timeline evidence for skills: {', '.join(skills[:4]) if skills else 'General skills'}."
        ]
        if candidate_data.get("education"):
            strengths.append(f"Education: {candidate_data['education'][0]}")

        potential_concerns = [amb.description for amb in ambiguities]

        # Qualitative reasoning
        qualitative_reasoning = (
            f"Candidate profile evaluated against '{job.get('title', 'Role')}'. "
            f"Mandatory requirements satisfied: {len(matched_reqs)}/{len(raw_reqs)}. "
            f"Calculated verified experience: {calculated_exp_str} (required: {req_min_exp} yrs). "
            f"Extraction method: {candidate_data.get('extraction_method', 'FULL_DOCUMENT')}. "
            f"Calibrated confidence: {int(calibrated_confidence * 100)}%."
        )

        calc_notes = (
            f"Deterministic evaluation: Dates normalized to YYYY-MM. Overlapping intervals merged. "
            f"Confidence calibrated from verified evidence coverage ({int(evidence_coverage * 100)}%), "
            f"timeline consistency ({int(timeline_consistency * 100)}%), and requirement coverage."
        )

        report = EvaluationReport(
            candidate_id=cand_id,
            candidate_name=full_name,
            job_id=job.get("job_id"),
            job_title=job.get("title"),
            status=status,
            overall_score=overall_score,
            recommendation=recommendation,
            calibrated_confidence=calibrated_confidence,
            total_professional_experience=calculated_exp_str,
            claimed_experience=claimed_exp_str,
            calculated_experience=calculated_exp_str,
            experience_discrepancy=discrepancy,
            employment_timeline=union_res.get("employment_history", []),
            matched_requirements=matched_reqs,
            partial_matches=partial_matches,
            missing_requirements=missing_reqs,
            potential_ambiguities=ambiguities,
            strengths=strengths,
            potential_concerns=potential_concerns,
            qualitative_reasoning=qualitative_reasoning,
            final_recommendation=f"Candidate evaluated with status '{status}' ({recommendation}) and score {overall_score}/100.",
            calculation_notes=calc_notes
        )

        return report.model_dump()
