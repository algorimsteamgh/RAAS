"""
Job Description Extractor
Uses Ollama to extract structured requirements from raw JD text.
Outputs editable structured data: required_experience, required_skills, preferred_skills, etc.
"""
import re
import logging
from typing import Dict, Any, Optional, List
from backend.app.services.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

JD_EXTRACTION_SYSTEM_PROMPT = """You are a structured Job Description analysis agent.
Your task is to extract structured requirements from a raw job description text.

CRITICAL RULES:
1. Extract ONLY what is explicitly stated in the JD. Do NOT infer or fabricate requirements.
2. Distinguish clearly between REQUIRED skills and PREFERRED/nice-to-have skills.
3. Extract minimum years of experience as a number. If "5+ years" → 5.0
4. Extract education requirements verbatim.
5. Extract employment type, location, and seniority if mentioned.

Respond ONLY with valid JSON following this schema:
{
  "title": "string - exact job title",
  "seniority": "string - Junior/Mid-level/Senior/Lead/Staff/Principal/Manager/Director",
  "department": "string or empty",
  "location": "string or empty",
  "employment_type": "Full-time/Part-time/Contract/Remote",
  "minimum_years_experience": number,
  "required_skills": ["string array of REQUIRED/MUST-HAVE skills"],
  "preferred_skills": ["string array of PREFERRED/NICE-TO-HAVE skills"],
  "education_requirements": ["string array"],
  "domain_requirements": ["string array - industry domains"],
  "responsibilities": ["string array of key responsibilities"],
  "other_constraints": "string - any other notable constraints"
}
"""


class JDExtractor:
    def __init__(self, ollama_client: Optional[OllamaClient] = None):
        self.client = ollama_client or OllamaClient()

    async def extract_requirements(self, jd_text: str) -> Dict[str, Any]:
        """
        Extract structured job requirements from raw JD text using Ollama.
        Falls back to heuristic extraction if Ollama is unavailable.
        """
        user_prompt = f"""Analyze the following Job Description and extract structured requirements.

JOB DESCRIPTION TEXT:
---
{jd_text}
---

Extract all requirements strictly from the text above. NO FABRICATION."""

        try:
            raw_json = await self.client.generate_json(
                prompt=user_prompt,
                system_prompt=JD_EXTRACTION_SYSTEM_PROMPT
            )
            return self._normalize_extraction(raw_json)
        except Exception as err:
            logger.warning(f"Ollama JD extraction failed ({err}). Using heuristic parser.")
            return self._heuristic_extraction(jd_text)

    def _normalize_extraction(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize and validate extracted JD data."""
        result = {
            "title": str(data.get("title", "Software Engineering Role")),
            "seniority": str(data.get("seniority", "Mid-level")),
            "department": str(data.get("department", "")),
            "location": str(data.get("location", "")),
            "employment_type": str(data.get("employment_type", "Full-time")),
            "minimum_years_experience": 0.0,
            "required_skills": [],
            "preferred_skills": [],
            "education_requirements": [],
            "domain_requirements": [],
            "responsibilities": [],
            "other_constraints": str(data.get("other_constraints", "")),
        }

        # Parse experience
        exp = data.get("minimum_years_experience", 0)
        try:
            result["minimum_years_experience"] = float(exp)
        except (ValueError, TypeError):
            # Try to extract number from string like "5+ years"
            match = re.search(r'(\d+(?:\.\d+)?)', str(exp))
            result["minimum_years_experience"] = float(match.group(1)) if match else 0.0

        # Normalize list fields
        for field in ["required_skills", "preferred_skills", "education_requirements", "domain_requirements", "responsibilities"]:
            val = data.get(field, [])
            if isinstance(val, list):
                result[field] = [str(v).strip() for v in val if v]
            elif isinstance(val, str):
                result[field] = [v.strip() for v in val.split(",") if v.strip()]
            else:
                result[field] = []

        # Also provide mandatory_skills alias
        result["mandatory_skills"] = result["required_skills"]

        return result

    def _heuristic_extraction(self, jd_text: str) -> Dict[str, Any]:
        """Fallback regex-based JD parser."""
        lines = jd_text.strip().splitlines()

        # Title: first non-empty line
        title = "Software Engineering Role"
        for line in lines[:5]:
            cleaned = line.strip()
            if cleaned and len(cleaned) < 80 and not any(kw in cleaned.lower() for kw in ["about", "we are", "company"]):
                title = cleaned
                break

        # Experience extraction
        exp_match = re.search(r'(\d+)\+?\s*(?:years?|yrs?)\s*(?:of)?\s*(?:experience|exp)', jd_text, re.IGNORECASE)
        min_exp = float(exp_match.group(1)) if exp_match else 0.0

        # Skills extraction (look for bullet points after "required", "must have", "qualifications")
        required_skills = []
        preferred_skills = []
        
        in_required = False
        in_preferred = False
        
        for line in lines:
            lower = line.lower().strip()
            if any(kw in lower for kw in ["required", "must have", "qualifications", "requirements", "essential"]):
                in_required = True
                in_preferred = False
                continue
            if any(kw in lower for kw in ["preferred", "nice to have", "bonus", "desired", "plus"]):
                in_preferred = True
                in_required = False
                continue
            if any(kw in lower for kw in ["responsibilities", "about", "benefits", "what you"]):
                in_required = False
                in_preferred = False
                continue

            # Extract skill from bullet point
            skill_match = re.match(r'^[\s•\-\*·]+(.+)', line)
            if skill_match:
                skill = skill_match.group(1).strip()
                if len(skill) > 2 and len(skill) < 100:
                    if in_preferred:
                        preferred_skills.append(skill)
                    elif in_required:
                        required_skills.append(skill)

        # Seniority
        seniority = "Mid-level"
        lower_text = jd_text.lower()
        if any(kw in lower_text for kw in ["senior", "sr.", "sr "]):
            seniority = "Senior"
        elif any(kw in lower_text for kw in ["junior", "jr.", "jr ", "entry"]):
            seniority = "Junior"
        elif any(kw in lower_text for kw in ["lead", "principal", "staff"]):
            seniority = "Lead"
        elif any(kw in lower_text for kw in ["manager", "director"]):
            seniority = "Manager"

        return {
            "title": title,
            "seniority": seniority,
            "department": "",
            "location": "",
            "employment_type": "Full-time",
            "minimum_years_experience": min_exp,
            "required_skills": required_skills[:15],
            "preferred_skills": preferred_skills[:10],
            "mandatory_skills": required_skills[:15],
            "education_requirements": [],
            "domain_requirements": [],
            "responsibilities": [],
            "other_constraints": "",
        }
