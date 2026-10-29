import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class ScoringEngine:
    """
    Deterministic scoring engine evaluating candidates against Job Descriptions.
    LLM outputs are NOT allowed to directly assign numerical scores.
    """
    def __init__(
        self,
        weight_mandatory: float = 0.40,
        weight_skills: float = 0.25,
        weight_experience: float = 0.20,
        weight_domain: float = 0.10,
        weight_preferred: float = 0.05
    ):
        self.w_mandatory = weight_mandatory
        self.w_skills = weight_skills
        self.w_experience = weight_experience
        self.w_domain = weight_domain
        self.w_preferred = weight_preferred

    def score_candidate(self, candidate: Dict[str, Any], job: Dict[str, Any]) -> Dict[str, Any]:
        cand_skills = set(s.lower() for s in candidate.get("skills", []))
        mand_skills = set(s.lower() for s in job.get("mandatory_skills", []))
        pref_skills = set(s.lower() for s in job.get("preferred_skills", []))
        
        cand_exp = float(candidate.get("years_experience") or 0.0)
        req_exp = float(job.get("minimum_years_experience") or 0.0)
        
        cand_domains = set(d.lower() for d in candidate.get("domains", []))
        req_domains = set(d.lower() for d in job.get("domain_requirements", []))

        # 1. Mandatory Skills Score (40%)
        matched_mand = mand_skills.intersection(cand_skills)
        missing_mand = mand_skills.difference(cand_skills)
        mandatory_score = (len(matched_mand) / len(mand_skills)) if mand_skills else 1.0

        # 2. Technical Skills Score (25%)
        skills_score = mandatory_score  # Base skill coverage

        # 3. Relevant Experience Score (20%)
        if req_exp == 0.0:
            exp_score = 1.0
        else:
            exp_ratio = cand_exp / req_exp
            exp_score = min(1.0, exp_ratio)

        # 4. Domain & Project Relevance (10%)
        if not req_domains:
            domain_score = 1.0
        else:
            domain_matches = cand_domains.intersection(req_domains)
            domain_score = 1.0 if domain_matches else 0.5

        # 5. Preferred Skills Score (5%)
        if not pref_skills:
            preferred_score = 1.0
        else:
            pref_matches = pref_skills.intersection(cand_skills)
            preferred_score = len(pref_matches) / len(pref_skills)

        # Total Composite Weighted Score (0.0 - 100.0%)
        total_score = (
            (mandatory_score * self.w_mandatory) +
            (skills_score * self.w_skills) +
            (exp_score * self.w_experience) +
            (domain_score * self.w_domain) +
            (preferred_score * self.w_preferred)
        ) * 100.0

        total_score = round(total_score, 1)

        # Assign Label
        if total_score >= 75.0 and len(missing_mand) == 0:
            recommendation = "SHORTLIST"
        elif total_score >= 50.0:
            recommendation = "REVIEW"
        else:
            recommendation = "DO_NOT_SHORTLIST"

        reasoning = (
            f"Mandatory Coverage: {len(matched_mand)}/{len(mand_skills)}. "
            f"Experience: {cand_exp} yrs (req {req_exp} yrs). "
            f"Missing Mandatory: {', '.join([s.title() for s in missing_mand]) if missing_mand else 'None'}."
        )

        return {
            "candidate_id": candidate.get("candidate_id"),
            "job_id": job.get("job_id"),
            "score": total_score,
            "recommendation": recommendation,
            "matched_skills": [s.title() for s in matched_mand],
            "missing_skills": [s.title() for s in missing_mand],
            "reasoning": reasoning,
            "score_breakdown": {
                "mandatory_score": round(mandatory_score * 100, 1),
                "skills_score": round(skills_score * 100, 1),
                "experience_score": round(exp_score * 100, 1),
                "domain_score": round(domain_score * 100, 1),
                "preferred_score": round(preferred_score * 100, 1)
            }
        }
