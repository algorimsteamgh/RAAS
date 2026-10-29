import logging
from typing import Dict, Any, List, Optional
from backend.app.services.matching_engine import MatchingEngine, RequirementStatus
from backend.app.services.experience_calculator import ExperienceCalculator

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS = {
    "experience_match": 0.30,
    "required_skills": 0.25,
    "job_requirements": 0.20,
    "achievements": 0.10,
    "career_progression": 0.05,
    "education": 0.05,
    "resume_quality": 0.05
}

MAX_POINTS = {
    "experience_match": 30,
    "required_skills": 25,
    "job_requirements": 20,
    "achievements": 10,
    "career_progression": 5,
    "education": 5,
    "resume_quality": 5,
}


class ExplainableScorer:
    @staticmethod
    def calculate_explainable_score(
        candidate_data: Dict[str, Any],
        job_data: Optional[Dict[str, Any]] = None,
        custom_weights: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        Calculates an explainable 0-100 score with explicit '+ / -' evidence breakdown,
        'Why This Candidate?', 'What is Missing?', 'Experience Truth', and per-factor breakdown.
        """
        weights = custom_weights or DEFAULT_WEIGHTS
        job = job_data or {
            "title": "Software Engineering Role",
            "seniority": "Mid-level",
            "minimum_years_experience": 3.0,
            "mandatory_skills": candidate_data.get("skills", [])[:3]
        }

        # Run Matching Engine
        match_data = MatchingEngine.match_candidate_against_job(candidate_data, job)
        req_analysis = match_data.get("requirement_analysis", [])
        graph = match_data.get("evidence_graph", {})

        # 1. Experience Match Factor (30%)
        calc_months = candidate_data.get("total_professional_experience_months", 0)
        req_exp_years = float(job.get("minimum_years_experience", 3.0))
        exp_ratio = min(1.0, (calc_months / 12.0) / max(0.5, req_exp_years))
        exp_score = round(exp_ratio * 100.0 * weights["experience_match"], 1)

        # 2. Required Skills Factor (25%)
        req_skills_analysis = [r for r in req_analysis if r["category"] == "REQUIRED_SKILL"]
        if req_skills_analysis:
            passed_skills = len([r for r in req_skills_analysis if r["status"] == RequirementStatus.PASS])
            partial_skills = len([r for r in req_skills_analysis if r["status"] in (RequirementStatus.PARTIAL, RequirementStatus.UNKNOWN)])
            skills_ratio = (passed_skills + 0.5 * partial_skills) / len(req_skills_analysis)
        else:
            skills_ratio = 1.0
        skills_score = round(skills_ratio * 100.0 * weights["required_skills"], 1)

        # 3. Overall Job Requirements Factor (20%)
        pass_count = len([r for r in req_analysis if r["status"] == RequirementStatus.PASS])
        job_req_ratio = pass_count / max(1, len(req_analysis))
        job_req_score = round(job_req_ratio * 100.0 * weights["job_requirements"], 1)

        # 4. Achievements Factor (10%)
        has_achievements = bool(candidate_data.get("projects") or candidate_data.get("evidence"))
        achieve_score = round((100.0 if has_achievements else 60.0) * weights["achievements"], 1)

        # 5. Career Progression Factor (5%)
        employment_history = candidate_data.get("employment_history", [])
        has_progression = len(employment_history) >= 2
        progr_score = round((90.0 if has_progression else 70.0) * weights["career_progression"], 1)

        # 6. Education Factor (5%)
        has_edu = bool(candidate_data.get("education"))
        edu_score = round((100.0 if has_edu else 50.0) * weights["education"], 1)

        # 7. Resume Quality Factor (5%)
        gaps = candidate_data.get("career_gaps", [])
        # Check for overlaps
        has_overlap = False
        if employment_history:
            from backend.app.services.experience_calculator import ExperienceCalculator as EC
            union_res = EC.calculate_total_experience_union(employment_history)
            has_overlap = union_res.get("has_overlap", False)
        
        qual_base = 90.0
        if gaps:
            qual_base -= 15.0
        if has_overlap:
            qual_base -= 10.0
        qual_score = round(qual_base * weights["resume_quality"], 1)

        overall_score = round(exp_score + skills_score + job_req_score + achieve_score + progr_score + edu_score + qual_score, 1)

        # Recommendation threshold mapping
        has_critical_fail = any(r["status"] == RequirementStatus.FAIL and r["category"] == "REQUIRED_SKILL" for r in req_analysis)
        
        if overall_score >= 90.0 and not has_critical_fail:
            recommendation = "Strong Match"
        elif overall_score >= 80.0 and not has_critical_fail:
            recommendation = "Match"
        elif overall_score >= 70.0:
            recommendation = "Possible Match"
        elif overall_score >= 55.0:
            recommendation = "Weak Match"
        else:
            recommendation = "Not a Match"

        # HERO FEATURE 1: "Why This Candidate?"
        why_factors = []
        calc_exp_str = candidate_data.get('total_professional_experience', '0 months')
        
        if calc_months >= req_exp_years * 12:
            why_factors.append({
                "factor": "Meets experience requirement",
                "detail": f"{calc_exp_str} verified (Required: {req_exp_years}+ yrs)",
                "evidence": f"Calculated from employment timeline using union-interval merging.",
                "confidence": "HIGH",
                "type": "pass"
            })
        
        for r in req_skills_analysis:
            if r["status"] == RequirementStatus.PASS:
                skill_name = r['requirement'].replace('Required Skill: ', '')
                why_factors.append({
                    "factor": f"Strong {skill_name} evidence",
                    "detail": r.get("calculated_experience", "Verified"),
                    "evidence": r["evidence_summary"],
                    "confidence": str(r.get("confidence", "HIGH")),
                    "type": "pass"
                })

        if candidate_data.get("education"):
            why_factors.append({
                "factor": "Education credentials verified",
                "detail": candidate_data["education"][0] if candidate_data["education"] else "",
                "evidence": "Extracted from education section of resume.",
                "confidence": "HIGH",
                "type": "pass"
            })

        if has_achievements:
            why_factors.append({
                "factor": "Demonstrates project/achievement evidence",
                "detail": f"{len(candidate_data.get('projects', []))} projects documented",
                "evidence": "Projects and achievements section present in resume.",
                "confidence": "MEDIUM",
                "type": "pass"
            })

        # HERO FEATURE 2: "What is Missing / Unverified?"
        missing_factors = []
        for r in req_analysis:
            if r["status"] == RequirementStatus.FAIL:
                status_label = "MISSING"
                missing_factors.append({
                    "requirement": r["requirement"].replace("Required Skill: ", "").replace("Preferred Skill: ", ""),
                    "status": status_label,
                    "category": r.get("category", ""),
                    "evidence": r["evidence_summary"],
                    "recommendation": f"Ask candidate about their {r['requirement'].replace('Required Skill: ', '').replace('Preferred Skill: ', '')} experience during interview."
                })
            elif r["status"] in (RequirementStatus.UNKNOWN, RequirementStatus.PARTIAL):
                status_label = "VERIFY"
                req_name = r["requirement"].replace("Required Skill: ", "").replace("Preferred Skill: ", "")
                missing_factors.append({
                    "requirement": req_name,
                    "status": status_label,
                    "category": r.get("category", ""),
                    "evidence": r["evidence_summary"],
                    "recommendation": f"{req_name} appears in resume but lacks sufficient employment-period evidence. Verify during interview."
                })

        if not missing_factors:
            missing_factors.append({
                "requirement": "None",
                "status": "PASS",
                "category": "",
                "evidence": "All core job requirements backed by verified evidence.",
                "recommendation": "Candidate meets all stated requirements."
            })

        # HERO FEATURE 3: "Experience Truth"
        claimed_years = candidate_data.get("years_experience")
        claimed_str = f"{claimed_years} years" if claimed_years is not None else "Not explicitly claimed"
        calc_str = candidate_data.get("total_professional_experience", "0 months")
        internship_str = candidate_data.get("internship_experience", "0 months")
        total_incl_intern = candidate_data.get("total_experience_including_internships", calc_str)

        # Calculate difference
        difference_str = "N/A"
        discrepancy_status = "No discrepancy"
        if claimed_years is not None:
            claimed_months = int(float(claimed_years) * 12)
            diff = claimed_months - calc_months
            if abs(diff) >= 6:
                difference_str = ExperienceCalculator.format_duration(abs(diff))
                discrepancy_status = "Timeline discrepancy"
            elif abs(diff) >= 2:
                difference_str = ExperienceCalculator.format_duration(abs(diff))
                discrepancy_status = "Minor difference"
            else:
                difference_str = "< 2 months"
                discrepancy_status = "Consistent"

        # Detect overlaps  
        overlap_details = []
        if employment_history and len(employment_history) >= 2:
            from backend.app.services.experience_calculator import DateNormalizer, extract_start_end_strings, CURRENT_YEAR, CURRENT_MONTH
            intervals_with_info = []
            for pos in employment_history:
                s_ym, e_ym, is_curr, is_valid = extract_start_end_strings(pos)
                if is_valid:
                    s_parsed, _ = DateNormalizer.parse_single_date(s_ym)
                    e_parsed = (CURRENT_YEAR, CURRENT_MONTH) if is_curr else DateNormalizer.parse_single_date(e_ym)[0]
                    if s_parsed and e_parsed:
                        s_idx = ExperienceCalculator.to_month_index(s_parsed[0], s_parsed[1])
                        e_idx = ExperienceCalculator.to_month_index(e_parsed[0], e_parsed[1])
                        intervals_with_info.append((s_idx, e_idx, str(pos.get("company", "Unknown")).strip()))
            
            intervals_with_info.sort(key=lambda x: x[0])
            for i in range(len(intervals_with_info) - 1):
                if intervals_with_info[i][1] >= intervals_with_info[i+1][0] and intervals_with_info[i][2].lower() != intervals_with_info[i+1][2].lower():
                    overlap_details.append({
                        "company_a": intervals_with_info[i][2],
                        "company_b": intervals_with_info[i+1][2],
                        "note": f"Concurrent employment detected between {intervals_with_info[i][2]} and {intervals_with_info[i+1][2]}. Recruiter review recommended."
                    })

        # Career gaps
        career_gaps = []
        if employment_history:
            career_gaps = ExperienceCalculator.calculate_career_gaps(employment_history)

        experience_truth = {
            "claimed_experience": claimed_str,
            "calculated_professional_experience": calc_str,
            "calculated_professional_experience_months": calc_months,
            "calculated_internship_experience": internship_str,
            "total_experience_including_internships": total_incl_intern,
            "difference": difference_str,
            "discrepancy_status": discrepancy_status,
            "current_company": candidate_data.get("current_company", "Not specified"),
            "current_title": candidate_data.get("current_title", "Not specified"),
            "current_employment_start_date": candidate_data.get("current_employment_start_date", "Not specified"),
            "notice_period": candidate_data.get("notice_period", "Not specified"),
            "has_timeline_overlap": has_overlap,
            "overlap_details": overlap_details,
            "career_gaps": career_gaps,
            "career_gap_count": len(career_gaps),
            "discrepancy_note": candidate_data.get("experience_discrepancy", "None")
        }

        # Score Breakdown with per-factor points
        positive_points = []
        negative_points = []
        
        for w in why_factors:
            positive_points.append(f"+ {w['factor']}")
        
        for m in missing_factors:
            if m["requirement"] != "None":
                prefix = "−" if m["status"] == "MISSING" else "⚠"
                negative_points.append(f"{prefix} {m['requirement']}: {m['status']}")

        return {
            "overall_score": overall_score,
            "recommendation": recommendation,
            "why_this_candidate": why_factors,
            "what_is_missing": missing_factors,
            "experience_truth": experience_truth,
            "employment_timeline": employment_history,
            "score_breakdown": {
                "positive_factors": positive_points,
                "negative_factors": negative_points,
                "factor_scores": {
                    "experience_match": {"score": exp_score, "max": MAX_POINTS["experience_match"], "label": "Experience"},
                    "required_skills": {"score": skills_score, "max": MAX_POINTS["required_skills"], "label": "Required Skills"},
                    "job_requirements": {"score": job_req_score, "max": MAX_POINTS["job_requirements"], "label": "Job Requirements"},
                    "achievements": {"score": achieve_score, "max": MAX_POINTS["achievements"], "label": "Achievements"},
                    "career_progression": {"score": progr_score, "max": MAX_POINTS["career_progression"], "label": "Career Progression"},
                    "education": {"score": edu_score, "max": MAX_POINTS["education"], "label": "Education"},
                    "resume_quality": {"score": qual_score, "max": MAX_POINTS["resume_quality"], "label": "Resume Quality"},
                }
            },
            "requirement_analysis": req_analysis,
            "evidence_graph": graph
        }
