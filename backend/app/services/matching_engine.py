import logging
from typing import Dict, Any, List, Optional
from backend.app.services.evidence_graph import EvidenceGraphEngine, ConfidenceLevel

logger = logging.getLogger(__name__)

class RequirementStatus:
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"

class MatchingEngine:
    @staticmethod
    def match_candidate_against_job(candidate_data: Dict[str, Any], job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates structured candidate evidence against job requirements.
        Determines PASS, PARTIAL, FAIL, UNKNOWN with evidence priority.
        """
        # Build Evidence Graph
        graph_data = EvidenceGraphEngine.build_candidate_evidence_graph(candidate_data)
        skill_graphs = graph_data.get("skill_graphs", {})

        req_results = []
        
        # 1. Experience Duration Requirement
        min_exp_years = float(job_data.get("minimum_years_experience") or job_data.get("required_experience_months", 0) / 12.0 or 0.0)
        calc_months = candidate_data.get("total_professional_experience_months", 0)
        calc_years = round(calc_months / 12.0, 1)

        if min_exp_years > 0:
            if calc_years >= min_exp_years:
                status = RequirementStatus.PASS
                conf = ConfidenceLevel.HIGH
                ev_str = f"Verified non-overlapping timeline: {candidate_data.get('total_professional_experience', f'{calc_years} years')}."
            elif calc_years >= min_exp_years * 0.7:
                status = RequirementStatus.PARTIAL
                conf = ConfidenceLevel.MEDIUM
                ev_str = f"Calculated timeline ({calc_years} yrs) is slightly below requirement ({min_exp_years} yrs)."
            else:
                status = RequirementStatus.FAIL
                conf = ConfidenceLevel.HIGH
                ev_str = f"Calculated timeline ({calc_years} yrs) falls short of required {min_exp_years} years."

            req_results.append({
                "requirement": f"Required Experience: {min_exp_years}+ years",
                "category": "EXPERIENCE",
                "calculated_experience": candidate_data.get("total_professional_experience", f"{calc_years} years"),
                "status": status,
                "confidence": conf,
                "evidence_summary": ev_str
            })

        # 2. Mandatory Required Skills
        mand_skills = job_data.get("mandatory_skills") or job_data.get("required_skills", [])
        for skill in mand_skills:
            sg = skill_graphs.get(skill)
            if sg:
                conf = sg.get("confidence", ConfidenceLevel.LOW)
                dur = sg.get("total_calculated_duration", "Insufficient evidence")
                nodes = sg.get("evidence_nodes", [])
                
                if conf == ConfidenceLevel.HIGH:
                    status = RequirementStatus.PASS
                    ev = nodes[0].get("source_text", f"Verified employment evidence for {skill}") if nodes else f"Verified {skill}"
                elif conf == ConfidenceLevel.MEDIUM:
                    status = RequirementStatus.PARTIAL
                    ev = f"Skill {skill} present in projects / summary but missing verified employment duration."
                else:
                    status = RequirementStatus.UNKNOWN
                    ev = f"Skill {skill} appears in Skills section only; no employment timeline evidence found."
            else:
                status = RequirementStatus.FAIL
                conf = ConfidenceLevel.HIGH
                dur = "0 months"
                ev = f"No evidence of {skill} found in candidate resume."

            req_results.append({
                "requirement": f"Required Skill: {skill}",
                "category": "REQUIRED_SKILL",
                "calculated_experience": dur if status == RequirementStatus.PASS else "Insufficient evidence",
                "status": status,
                "confidence": conf,
                "evidence_summary": ev
            })

        # 3. Preferred / Nice-to-have Skills
        pref_skills = job_data.get("preferred_skills", [])
        for skill in pref_skills:
            sg = skill_graphs.get(skill)
            if sg:
                conf = sg.get("confidence", ConfidenceLevel.LOW)
                status = RequirementStatus.PASS if conf in [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM] else RequirementStatus.PARTIAL
                ev = sg.get("reasoning", f"Demonstrates {skill} experience")
            else:
                status = RequirementStatus.FAIL
                conf = ConfidenceLevel.LOW
                ev = f"Preferred skill {skill} not listed"

            req_results.append({
                "requirement": f"Preferred Skill: {skill}",
                "category": "PREFERRED_SKILL",
                "calculated_experience": sg.get("total_calculated_duration", "0 months") if sg else "0 months",
                "status": status,
                "confidence": conf,
                "evidence_summary": ev
            })

        return {
            "requirement_analysis": req_results,
            "evidence_graph": graph_data
        }
