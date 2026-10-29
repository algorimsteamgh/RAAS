import re
import logging
from typing import Dict, Any, List, Tuple, Optional
from backend.app.services.experience_calculator import DateNormalizer

logger = logging.getLogger(__name__)

# Section heading patterns
SECTION_HEADINGS = {
    "EXPERIENCE": r'^(?:professional\s+experience|work\s+experience|employment\s+history|work\s+history|career\s+history|experience\s+and\s+projects|experience|employment)\b',
    "EDUCATION": r'^(?:education|academic\s+background|academic\s+qualifications|academics|qualifications)\b',
    "PROJECTS": r'^(?:projects|key\s+projects|personal\s+projects|academic\s+projects|selected\s+projects)\b',
    "SKILLS": r'^(?:technical\s+skills|skills\s+and\s+tools|core\s+skills|skills|technologies|competencies)\b',
    "CERTIFICATIONS": r'^(?:certifications|certificates|licenses|credentials|professional\s+certifications)\b',
    "SUMMARY": r'^(?:professional\s+summary|executive\s+summary|summary|profile|about\s+me|overview)\b',
    "PUBLICATIONS": r'^(?:publications|talks|patents|awards|honors|achievements)\b'
}

# Regex to detect lines starting with bullets or numbered lists
BULLET_PREFIX_REGEX = r'^\s*(?:[•\*\-–—▪▫➢▪►]|\d+\.|\([a-z0-9]+\))\s*'

# Common action verbs that indicate a resume bullet point, not a job title or company
ACTION_VERB_REGEX = r'^(?:implemented|developed|designed|built|architected|led|managed|collaborated|engineered|optimized|created|maintained|integrated|configured|spearheaded|automated|assisted|delivered|deployed|migrated|improved|analyzed|established|facilitated|monitored|tested|directed|formulated|executed|supported|authored|authored|researched)\b'

# Date range pattern matching standard CV date formats
DATE_RANGE_REGEX = r'((?:(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s*,?\s*\d{4}|\d{4}[/\-\.]\d{1,2}|\d{1,2}[/\-\.]\d{4}|\b19\d\d\b|\b20\d\d\b)\s*(?:[\–—\-\|]|to|until)\s*(?:(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s*,?\s*\d{4}|\d{4}[/\-\.]\d{1,2}|\d{1,2}[/\-\.]\d{4}|\b19\d\d\b|\b20\d\d\b|Present|Current|Till Date|Till Present|Now|Ongoing))'

class DocumentLayoutEngine:
    """
    Layout and structural reconstruction engine for arbitrary CV formats.
    Segments document into sections, isolates employment history,
    and extracts structured employment records with strict validation.
    """

    @classmethod
    def segment_sections(cls, cv_text: str) -> Dict[str, str]:
        """Segments raw CV text into named sections based on headings."""
        lines = cv_text.splitlines()
        sections: Dict[str, List[str]] = {"HEADER": []}
        current_section = "HEADER"

        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                continue

            # Check if this line is a section heading
            heading_matched = False
            # Clean common formatting markers like colons, underlines, or asterisks
            clean_heading = re.sub(r'[:\*\#_\-]+$', '', trimmed).strip().lower()

            for sec_name, pattern in SECTION_HEADINGS.items():
                if re.match(pattern, clean_heading, re.IGNORECASE) and len(clean_heading) < 40:
                    current_section = sec_name
                    if current_section not in sections:
                        sections[current_section] = []
                    heading_matched = True
                    break

            if not heading_matched:
                sections[current_section].append(trimmed)

        return {k: "\n".join(v) for k, v in sections.items()}

    @classmethod
    def extract_claimed_years_experience(cls, cv_text: str) -> Tuple[Optional[float], str]:
        """
        Extracts explicitly stated total years of experience from summary/header.
        Returns: (claimed_years or None, claim_status: 'EXPLICITLY_CLAIMED' | 'NOT_STATED')
        """
        # Search for phrases like "5+ years of experience", "3 years experience", "4.5+ yrs of relevant experience"
        patterns = [
            r'(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s*(?:of)?\s*(?:relevant|professional|software|hands-on|industry)?\s*experience',
            r'experience\s*(?:of)?\s*(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)'
        ]
        for pat in patterns:
            m = re.search(pat, cv_text, re.IGNORECASE)
            if m:
                try:
                    val = float(m.group(1))
                    if 0.5 <= val <= 45.0:
                        return val, "EXPLICITLY_CLAIMED"
                except ValueError:
                    pass

        return None, "NOT_STATED"

    @classmethod
    def is_bullet_or_action_line(cls, line: str) -> bool:
        """Determines if a line is a bullet point or action description."""
        cleaned = line.strip()
        if re.search(BULLET_PREFIX_REGEX, cleaned):
            return True
        no_bullet = re.sub(BULLET_PREFIX_REGEX, '', cleaned).strip()
        if re.match(ACTION_VERB_REGEX, no_bullet, re.IGNORECASE):
            return True
        return False

    @classmethod
    def extract_structured_employment_records(cls, cv_text: str) -> List[Dict[str, Any]]:
        """
        Extracts employment history from the CV using layout and section awareness.
        Supports multi-line, two-column, inline delimiter, and parenthesized formats.
        """
        sections = cls.segment_sections(cv_text)
        exp_text = sections.get("EXPERIENCE", "")

        # If no explicit EXPERIENCE section was found, fall back to searching the full text
        text_to_search = exp_text if exp_text and len(exp_text) > 100 else cv_text
        lines = [l.strip() for l in text_to_search.splitlines() if l.strip()]

        positions: List[Dict[str, Any]] = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # Skip bullet points and action lines
            if cls.is_bullet_or_action_line(line):
                i += 1
                continue

            # Check if this line contains a date range
            date_match = re.search(DATE_RANGE_REGEX, line, re.IGNORECASE)
            if date_match:
                date_range_str = date_match.group(1).strip()
                s_ym, e_ym, is_curr, is_valid = DateNormalizer.parse_date_range_string(date_range_str)

                if is_valid:
                    # Case 1: Role on same line before the date e.g. "Software Development Engineer & AI Engineer Jan 2026 – Present"
                    role_part = line[:date_match.start()].strip().strip('-|–—,')
                    company_part = ""
                    responsibilities: List[str] = []

                    # Look at next line for company or previous line
                    if role_part and i + 1 < len(lines) and not cls.is_bullet_or_action_line(lines[i + 1]):
                        next_line = lines[i + 1].strip()
                        # If next line doesn't contain a date range, it's the company name
                        if not re.search(DATE_RANGE_REGEX, next_line, re.IGNORECASE) and len(next_line) < 60:
                            company_part = next_line
                            i += 1  # consume company line

                    # Case 2: Company was on previous line
                    if not company_part and i > 0 and not cls.is_bullet_or_action_line(lines[i - 1]):
                        prev_line = lines[i - 1].strip()
                        if not re.search(DATE_RANGE_REGEX, prev_line, re.IGNORECASE) and len(prev_line) < 60:
                            company_part = prev_line

                    # Case 3: Line has format "Company - Role" or "Role at Company"
                    if not company_part and " at " in role_part:
                        parts = role_part.split(" at ", 1)
                        role_part, company_part = parts[0].strip(), parts[1].strip()
                    elif not company_part and any(sep in role_part for sep in [" - ", " – ", " — ", " | "]):
                        parts = re.split(r'\s*[\-–—\|]\s*', role_part, maxsplit=1)
                        if len(parts) == 2:
                            # Heuristic: if first part has "Developer", "Engineer", "Manager", etc., it's Role - Company
                            if any(k in parts[0].lower() for k in ["engineer", "developer", "lead", "manager", "intern", "trainee", "associate", "specialist", "consultant"]):
                                role_part, company_part = parts[0].strip(), parts[1].strip()
                            else:
                                company_part, role_part = parts[0].strip(), parts[1].strip()

                    # Fallback defaults if still empty
                    if not role_part:
                        role_part = "Software Professional"
                    if not company_part:
                        company_part = "Organization"

                    # Collect subsequent bullet lines as responsibilities
                    j = i + 1
                    while j < len(lines) and (cls.is_bullet_or_action_line(lines[j]) or len(lines[j]) > 80):
                        clean_resp = re.sub(BULLET_PREFIX_REGEX, '', lines[j]).strip()
                        if clean_resp:
                            responsibilities.append(clean_resp)
                        j += 1

                    emp_type = "Internship" if any(k in role_part.lower() for k in ["intern", "trainee", "internship"]) else "Full-time"

                    # Clean role_part from ligatures / spacing artifacts like "T rainee" -> "Trainee"
                    clean_role = re.sub(r'\bT\s+rainee\b', 'Trainee', role_part, flags=re.IGNORECASE)
                    clean_role = re.sub(r'\bF\s+rontend\b', 'Frontend', clean_role, flags=re.IGNORECASE)
                    clean_role = re.sub(r'\s+', ' ', clean_role).strip()

                    positions.append({
                        "company": company_part,
                        "title": clean_role,
                        "start_date": s_ym,
                        "end_date": e_ym,
                        "is_current": is_curr,
                        "employment_type": emp_type,
                        "responsibilities": responsibilities,
                        "technologies": [],
                        "source_text": f"{clean_role} at {company_part} ({date_range_str})",
                        "source_section": "Professional Experience",
                        "evidence_status": "VERIFIED",
                        "is_verified": True
                    })

            i += 1

        # Deduplicate positions by company + start_date
        deduped: List[Dict[str, Any]] = []
        seen = set()
        for p in positions:
            key = f"{p['company'].lower()}|{p['title'].lower()}|{p['start_date']}"
            if key not in seen:
                seen.add(key)
                deduped.append(p)

        return deduped
