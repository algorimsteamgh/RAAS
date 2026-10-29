import logging
import json
from typing import Dict, Any, List, Optional
from backend.app.services.ollama_client import OllamaClient
from backend.app.config import settings

logger = logging.getLogger(__name__)

class HRChatAgent:
    """
    Interactive HR Candidate Intelligence Agent.
    Allows recruiters to chat about candidate resumes, match evaluation feedback,
    skills, timeline gaps, and draft interview questions or email communications.
    """
    def __init__(self, ollama_client: Optional[OllamaClient] = None):
        self.ollama = ollama_client or OllamaClient()

    async def answer_query(
        self,
        candidate_data: Dict[str, Any],
        user_message: str,
        job_data: Optional[Dict[str, Any]] = None,
        evaluation_data: Optional[Dict[str, Any]] = None,
        history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Generates an evidence-grounded response for HR queries regarding a candidate.
        """
        system_prompt = self._build_system_prompt(candidate_data, job_data, evaluation_data)
        user_prompt = self._build_user_prompt(user_message, history)

        try:
            response_text = await self.ollama.generate_text(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.3
            )
            if not response_text or len(response_text.strip()) == 0:
                raise ValueError("Empty response from Ollama")
        except Exception as e:
            logger.warning(f"Ollama chat generation failed ({e}). Using deterministic heuristic fallback.")
            response_text = self._heuristic_fallback_response(user_message, candidate_data, job_data, evaluation_data)

        # Generate intelligent contextual follow-up suggestions
        suggested_followups = self._generate_suggested_followups(user_message, candidate_data, job_data, evaluation_data)

        return {
            "response": response_text,
            "suggested_followups": suggested_followups
        }

    def _format_items(self, items: Any) -> str:
        if not items:
            return "Not specified"
        if isinstance(items, str):
            return items
        if not isinstance(items, list):
            return str(items)
        formatted = []
        for item in items:
            if isinstance(item, str):
                formatted.append(item)
            elif isinstance(item, dict):
                deg = item.get("degree") or item.get("name") or item.get("title") or ""
                inst = item.get("institution") or item.get("school") or item.get("issuer") or ""
                yr = item.get("year") or item.get("date") or ""
                parts = [p for p in [deg, f"({inst})" if inst else "", str(yr) if yr else ""] if p]
                formatted.append(" ".join(parts) if parts else str(item))
            else:
                formatted.append(str(item))
        return ", ".join(formatted) if formatted else "Not specified"

    def _build_system_prompt(
        self,
        candidate: Dict[str, Any],
        job: Optional[Dict[str, Any]],
        eval_data: Optional[Dict[str, Any]]
    ) -> str:
        name = candidate.get("full_name") or candidate.get("name") or "the candidate"
        title = candidate.get("current_title") or (candidate.get("roles", [""])[0] if candidate.get("roles") else "Professional")
        skills = candidate.get("skills", [])
        calc_exp = candidate.get("total_professional_experience") or f"{candidate.get('years_experience', 0)} years"
        claimed_exp = candidate.get("candidate_claimed_experience")
        
        emp_list = candidate.get("work_experience") or candidate.get("employment_history") or []
        emp_history_summary = []
        for emp in emp_list:
            comp = emp.get("company", "Company")
            role = emp.get("title") or emp.get("role", "Role")
            start = emp.get("start_date", "")
            end = "Present" if emp.get("is_current") else emp.get("end_date", "")
            techs = ", ".join(emp.get("technologies", [])[:5])
            tech_str = f" [Tech: {techs}]" if techs else ""
            emp_history_summary.append(f"- {role} at {comp} ({start} - {end}){tech_str}")

        history_str = "\n".join(emp_history_summary) if emp_history_summary else "None listed"

        job_context = ""
        if job:
            job_context = f"""
TARGET JOB REQUISITION:
- Title: {job.get('title')} ({job.get('seniority', 'Mid-level')})
- Mandatory Requirements: {', '.join(job.get('mandatory_skills', []) or job.get('required_skills', []))}
- Preferred Skills: {', '.join(job.get('preferred_skills', []))}
- Minimum Experience: {job.get('minimum_years_experience', 0)} years
- Domain Requirements: {', '.join(job.get('domain_requirements', []))}
"""

        eval_context = ""
        if eval_data:
            eval_context = f"""
EVALUATION RESULTS FOR THIS JOB:
- Composite Score: {eval_data.get('score', eval_data.get('overall_score', 'N/A'))} / 100
- Recommendation: {eval_data.get('recommendation', 'REVIEW')}
- Matched Skills: {', '.join(eval_data.get('matched_skills', []))}
- Missing Skills: {', '.join(eval_data.get('missing_skills', []))}
- Deterministic Reasoning: {eval_data.get('reasoning', '')}
"""

        return f"""You are an expert HR Recruiting Assistant and Candidate Intelligence Agent for the Local AI CV Screening Platform.
You are assisting a human recruiter evaluating candidate: {name}.

CANDIDATE VERIFIED DATA:
- Full Name: {name}
- Current Title: {title}
- Location: {candidate.get('location', 'Not specified')}
- Email: {candidate.get('email', 'Not specified')}
- Notice Period / Availability: {candidate.get('notice_period', 'Not specified')}
- Verified Non-Overlapping Experience: {calc_exp}
- Claimed Experience in Summary: {f'{claimed_exp} years' if claimed_exp else 'Not explicitly claimed'}
- Extracted Technical Skills: {', '.join(skills[:30])}
- Education: {self._format_items(candidate.get('education'))}
- Certifications: {self._format_items(candidate.get('certifications'))}
- Employment History:
{history_str}
{job_context}
{eval_context}

RULES OF ENGAGEMENT:
1. Grounding: Answer strictly using facts from the candidate's resume and job evaluation data above.
2. Honesty on Gaps: If a skill, degree, or experience is not present in the CV, clearly state that there is no evidence of it in the resume. Never hallucinate qualifications.
3. Tenure Arithmetic: Always refer to the verified non-overlapping tenure ({calc_exp}). Note any discrepancy if claimed experience differs from chronological tenure.
4. Professional HR Assistance: You can answer questions, summarize strengths/weaknesses, draft personalized outreach emails, and formulate technical interview questions.
5. Formatting: Use clean Markdown with bold bullet points for fast scannability by busy recruiters.
"""

    def _build_user_prompt(self, message: str, history: Optional[List[Dict[str, str]]]) -> str:
        prompt_parts = []
        if history:
            prompt_parts.append("CONVERSATION HISTORY:")
            for turn in history[-6:]:  # Keep last 3 exchanges
                role = "Recruiter" if turn.get("role") == "user" else "AI Agent"
                prompt_parts.append(f"{role}: {turn.get('content', '')}")
            prompt_parts.append("")

        prompt_parts.append(f"Recruiter: {message}\nAI Agent:")
        return "\n".join(prompt_parts)

    def _heuristic_fallback_response(
        self,
        message: str,
        candidate: Dict[str, Any],
        job: Optional[Dict[str, Any]],
        eval_data: Optional[Dict[str, Any]]
    ) -> str:
        msg_lower = message.lower()
        name = candidate.get("full_name") or candidate.get("name") or "The candidate"
        skills = candidate.get("skills", [])
        calc_exp = candidate.get("total_professional_experience") or f"{candidate.get('years_experience', 0)} years"

        if any(w in msg_lower for w in ["score", "why", "recommendation", "review", "shortlist", "reject"]):
            if eval_data:
                rec = eval_data.get("recommendation", "REVIEW")
                score = eval_data.get("score", eval_data.get("overall_score", 0))
                matched = eval_data.get("matched_skills", [])
                missing = eval_data.get("missing_skills", [])
                reasoning = eval_data.get("reasoning", "")
                
                resp = [
                    f"### Evaluation Feedback for {name}\n",
                    f"**Overall Match Score:** {score}% — **Recommendation:** `{rec}`\n",
                    f"**Key Rationale:** {reasoning}\n",
                    f"- **Matched Qualifications:** {', '.join(matched) if matched else 'None'}",
                    f"- **Missing Requirements:** {', '.join(missing) if missing else 'None'}",
                    f"- **Verified Non-Overlapping Experience:** {calc_exp}"
                ]
                if missing and rec != "SHORTLIST":
                    resp.append(f"\n> **Note:** Under our deterministic scoring guardrail, missing any mandatory requirements prevents an automatic `SHORTLIST` recommendation.")
                return "\n".join(resp)
            else:
                return f"**{name}** has **{calc_exp}** of verified experience with primary skills including: {', '.join(skills[:8])}. To get a specific match score, select a target Job Description in the 'Match JD' tool."

        elif any(w in msg_lower for w in ["strength", "highlight", "pro", "good"]):
            emp_list = candidate.get("work_experience") or candidate.get("employment_history") or []
            roles = [emp.get("title") for emp in emp_list if emp.get("title")]
            return f"### Key Strengths of {name}\n\n" \
                   f"- **Verified Experience:** {calc_exp} in professional software/technical roles.\n" \
                   f"- **Core Technical Stack:** {', '.join(skills[:10])}.\n" \
                   f"- **Career Progression:** Demonstrated roles including {', '.join(roles[:3]) if roles else 'technical contributor'}.\n" \
                   f"- **Education:** {self._format_items(candidate.get('education'))}."

        elif any(w in msg_lower for w in ["gap", "weakness", "concern", "risk", "missing"]):
            missing = eval_data.get("missing_skills", []) if eval_data else []
            claimed = candidate.get("candidate_claimed_experience")
            calc_years = candidate.get("years_experience", 0)
            
            concerns = []
            if missing:
                concerns.append(f"- **Missing Requisition Skills:** Lacks documented evidence for: {', '.join(missing)}.")
            if claimed and abs(float(claimed) - float(calc_years)) >= 1.0:
                concerns.append(f"- **Experience Discrepancy:** Candidate summary claims {claimed} years, but chronological timeline totals ~{calc_years:.1f} years.")
            if not candidate.get("education"):
                concerns.append("- **Education:** No accredited degree explicitly parsed from the resume text.")
            if not concerns:
                concerns.append("- No critical red flags detected in timeline consistency or verified credentials.")
                
            return f"### Areas to Verify & Potential Gaps for {name}\n\n" + "\n".join(concerns)

        elif any(w in msg_lower for w in ["email", "invite", "draft", "outreach", "message"]):
            job_title = job.get("title", "our open position") if job else "our technical role"
            return f"### Draft Phone Screen Invitation for {name}\n\n" \
                   f"**Subject:** Interview Invitation: {job_title} at our team\n\n" \
                   f"Hi {name.split()[0] if name else 'there'},\n\n" \
                   f"Thank you for sharing your resume with us. Our team was impressed by your background in {', '.join(skills[:3])} and your experience as a {candidate.get('current_title', 'technical professional')}.\n\n" \
                   f"We would love to schedule a brief 20-minute introductory phone conversation to discuss the **{job_title}** opportunity and learn more about your recent projects.\n\n" \
                   f"Please let us know a few times that work for you over the next few days.\n\n" \
                   f"Best regards,\n" \
                   f"Recruiting Team"

        elif any(w in msg_lower for w in ["question", "interview", "probe", "ask"]):
            return f"### Recommended Technical & Timeline Verification Questions for {name}\n\n" \
                   f"1. **Core Competency:** Can you walk us through a complex project where you designed architecture using {skills[0] if skills else 'your primary stack'}?\n" \
                   f"2. **Production Scale:** What was the highest throughput or concurrency your recent services handled?\n" \
                   f"3. **Timeline Verification:** Walk us through your transition between your recent roles at {candidate.get('employment_history', [{}])[0].get('company', 'your recent employer')}.\n" \
                   f"4. **Technical Trade-offs:** Tell us about a time you had to refactor or rebuild a legacy system under tight deadlines."

        # Default summary
        return f"**{name}** is a **{candidate.get('current_title', 'Professional')}** based in {candidate.get('location', 'their area')} with **{calc_exp}** of verified experience. " \
               f"Key skills include: {', '.join(skills[:8])}. Feel free to ask about their specific skill coverage, score explanation, interview questions, or email outreach!"

    def _generate_suggested_followups(
        self,
        message: str,
        candidate: Dict[str, Any],
        job: Optional[Dict[str, Any]],
        eval_data: Optional[Dict[str, Any]]
    ) -> List[str]:
        msg_lower = message.lower()
        if "score" in msg_lower or "why" in msg_lower:
            return [
                "What are this candidate's biggest technical strengths?",
                "What red flags or gaps should I probe?",
                "Draft a phone screen invitation email"
            ]
        elif "strength" in msg_lower:
            return [
                "What are the main risks or missing skills?",
                "Suggest 3 technical interview questions",
                "Does this candidate have team lead experience?"
            ]
        elif "gap" in msg_lower or "weakness" in msg_lower:
            return [
                "What questions should I ask about these gaps in the interview?",
                "Why was this candidate given their match score?",
                "Draft a polite rejection email"
            ]
        elif "email" in msg_lower or "invite" in msg_lower:
            return [
                "Suggest 3 technical interview questions for the phone screen",
                "Summarize their career progression timeline",
                "Explain why they received their match score"
            ]
        else:
            return [
                "Why was this candidate given their score?",
                "What are their main technical strengths?",
                "What red flags or gaps should I ask about?",
                "Draft a phone screen invitation email"
            ]
