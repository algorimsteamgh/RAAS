import re
import datetime
import logging
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

CURRENT_YEAR = 2026
CURRENT_MONTH = 8  # August 2026

MONTH_MAP = {
    'jan': 1, 'january': 1, 'jan.': 1,
    'feb': 2, 'february': 2, 'feb.': 2,
    'mar': 3, 'march': 3, 'mar.': 3,
    'apr': 4, 'april': 4, 'apr.': 4,
    'may': 5, 'may.': 5,
    'jun': 6, 'june': 6, 'jun.': 6,
    'jul': 7, 'july': 7, 'jul.': 7,
    'aug': 8, 'august': 8, 'aug.': 8,
    'sep': 9, 'september': 9, 'sept': 9, 'sep.': 9, 'sept.': 9,
    'oct': 10, 'october': 10, 'oct.': 10,
    'nov': 11, 'november': 11, 'nov.': 11,
    'dec': 12, 'december': 12, 'dec.': 12
}

CURRENT_TERMS = {'present', 'current', 'till date', 'till present', 'now', 'today', 'ongoing', 'current - ongoing'}

class DateNormalizer:
    """
    Centralized, deterministic date normalization service.
    Normalizes arbitrary date strings into canonical 'YYYY-MM' format,
    handling current employment, partial dates, and range expressions.
    """

    @classmethod
    def is_current_term(cls, text: Optional[str]) -> bool:
        if not text:
            return False
        clean = text.strip().lower()
        return any(term == clean or term in clean for term in CURRENT_TERMS)

    @classmethod
    def parse_single_date(cls, date_str: Optional[str]) -> Tuple[Optional[Tuple[int, int]], bool]:
        """
        Parses a single date string into ((year, month), is_approximate).
        Returns (None, True) if date cannot be parsed.
        """
        if not date_str or not isinstance(date_str, str):
            return None, True

        s = date_str.strip()
        if not s or s.lower() in ('unknown', 'null', 'none', 'n/a', '?'):
            return None, True

        # Check for current employment terms
        if cls.is_current_term(s):
            return (CURRENT_YEAR, CURRENT_MONTH), False

        # Pattern 1: Month Name + Year e.g. "Jan 2026", "January 2026", "Jul, 2025", "Sep. 2022"
        month_name_match = re.search(r'\b([a-zA-Z]{3,9}\.?)\s*,?\s*(\d{4})\b', s)
        if month_name_match:
            m_str = month_name_match.group(1).lower()
            y_int = int(month_name_match.group(2))
            m_int = MONTH_MAP.get(m_str) or MONTH_MAP.get(m_str.rstrip('.')) or 1
            if 1950 <= y_int <= CURRENT_YEAR + 1:
                return (y_int, m_int), False

        # Pattern 2: Year + Month Name e.g. "2026 Jan", "2025 July"
        rev_month_match = re.search(r'\b(\d{4})\s*,?\s*([a-zA-Z]{3,9}\.?)\b', s)
        if rev_month_match:
            y_int = int(rev_month_match.group(1))
            m_str = rev_month_match.group(2).lower()
            m_int = MONTH_MAP.get(m_str) or MONTH_MAP.get(m_str.rstrip('.')) or 1
            if 1950 <= y_int <= CURRENT_YEAR + 1:
                return (y_int, m_int), False

        # Pattern 3: YYYY-MM or YYYY/MM or YYYY.MM (ISO-like)
        iso_match = re.search(r'\b(\d{4})[/\-\.](\d{1,2})\b', s)
        if iso_match:
            y_int = int(iso_match.group(1))
            m_int = int(iso_match.group(2))
            if 1950 <= y_int <= CURRENT_YEAR + 1 and 1 <= m_int <= 12:
                return (y_int, m_int), False

        # Pattern 4: MM/YYYY or MM-YYYY or MM.YYYY
        num_date_match = re.search(r'\b(\d{1,2})[/\-\.](\d{4})\b', s)
        if num_date_match:
            m_int = int(num_date_match.group(1))
            y_int = int(num_date_match.group(2))
            if 1950 <= y_int <= CURRENT_YEAR + 1 and 1 <= m_int <= 12:
                return (y_int, m_int), False

        # Pattern 5: Year only e.g. "2024", "2020"
        year_match = re.search(r'\b(19\d\d|20\d\d)\b', s)
        if year_match:
            y_int = int(year_match.group(1))
            if 1950 <= y_int <= CURRENT_YEAR + 1:
                return (y_int, 1), True

        return None, True

    @classmethod
    def normalize_to_ym_string(cls, date_str: Optional[str]) -> Optional[str]:
        """Converts an arbitrary single date into 'YYYY-MM' or None."""
        ym, _ = cls.parse_single_date(date_str)
        if ym:
            return f"{ym[0]}-{ym[1]:02d}"
        return None

    @classmethod
    def parse_date_range_string(cls, range_str: str) -> Tuple[Optional[str], Optional[str], bool, bool]:
        """
        Parses an arbitrary date range string (e.g. "Jan 2026 – Present", "Jul 2025 - Dec 2025", "2020–2024", "2025-07 - 2025-12").
        Returns: (start_date_ym, end_date_ym, is_current, is_valid)
        """
        if not range_str or not isinstance(range_str, str):
            return None, None, False, False

        s = range_str.strip()

        # Split on explicit range separators: en-dash, em-dash, "to", "until", pipe, or hyphen with surrounding space
        parts = re.split(r'\s+(?:to|until)\s+|\s*[\–—]\s*|\s+[\-\|]\s*', s, maxsplit=1)

        # If no split with spaces, check for year-range like "2020-2024" or "2020–2024"
        if len(parts) == 1:
            year_range_match = re.match(r'^\s*(\d{4})\s*[\-\–—]\s*(\d{4})\s*$', s)
            if year_range_match:
                parts = [year_range_match.group(1), year_range_match.group(2)]

        if len(parts) == 2:
            start_raw, end_raw = parts[0].strip(), parts[1].strip()
            is_current = cls.is_current_term(end_raw)
            start_ym = cls.normalize_to_ym_string(start_raw)
            end_ym = None if is_current else cls.normalize_to_ym_string(end_raw)
            is_valid = bool(start_ym and (is_current or end_ym))
            return start_ym, end_ym, is_current, is_valid
        elif len(parts) == 1:
            val = parts[0].strip()
            if cls.is_current_term(val):
                return None, None, True, False
            single_ym = cls.normalize_to_ym_string(val)
            if single_ym:
                return single_ym, None, False, True

        return None, None, False, False

def extract_start_end_strings(pos: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], bool, bool]:
    """
    Extracts and normalizes start_date, end_date, is_current, and is_valid from position dict.
    """
    is_current = bool(pos.get("is_current"))
    start_raw = pos.get("start_date") or pos.get("start")
    end_raw = pos.get("end_date") or pos.get("end")
    dates_raw = pos.get("dates") or pos.get("date_range")

    # If dates_raw is given as a range string
    if dates_raw and (not start_raw or not end_raw):
        s_ym, e_ym, curr, valid = DateNormalizer.parse_date_range_string(str(dates_raw))
        if valid:
            return s_ym, e_ym, curr, True

    # Parse individual start and end dates
    if start_raw:
        s_ym = DateNormalizer.normalize_to_ym_string(str(start_raw))
    else:
        s_ym = None

    if end_raw:
        if DateNormalizer.is_current_term(str(end_raw)):
            is_current = True
            e_ym = None
        else:
            e_ym = DateNormalizer.normalize_to_ym_string(str(end_raw))
    else:
        e_ym = None

    is_valid = bool(s_ym and (is_current or e_ym))
    return s_ym, e_ym, is_current, is_valid

class DateParser:
    @staticmethod
    def parse_date(date_str: Optional[str], default_to_current: bool = False) -> Tuple[Optional[Tuple[int, int]], bool]:
        if not date_str:
            if default_to_current:
                return (CURRENT_YEAR, CURRENT_MONTH), False
            return None, True
        
        if DateNormalizer.is_current_term(date_str):
            return (CURRENT_YEAR, CURRENT_MONTH), False
            
        return DateNormalizer.parse_single_date(date_str)

class ExperienceCalculator:
    @staticmethod
    def to_month_index(year: int, month: int) -> int:
        return year * 12 + month

    @staticmethod
    def format_duration(total_months: int) -> str:
        if total_months <= 0:
            return "0 months"
        years = total_months // 12
        months = total_months % 12
        
        parts = []
        if years > 0:
            parts.append(f"{years} year{'s' if years > 1 else ''}")
        if months > 0:
            parts.append(f"{months} month{'s' if months > 1 else ''}")
        return " ".join(parts) if parts else "0 months"

    @staticmethod
    def calculate_position_duration(start_str: Optional[str], end_str: Optional[str], is_current: bool = False) -> Dict[str, Any]:
        """Calculates duration in months and formatted string for a position."""
        start_ym, _ = DateNormalizer.parse_single_date(start_str)
        if is_current:
            end_ym = (CURRENT_YEAR, CURRENT_MONTH)
        else:
            end_ym, _ = DateNormalizer.parse_single_date(end_str)

        if not start_ym or not end_ym:
            return {
                "start_normalized": start_str or "Date not verified",
                "end_normalized": "Present" if is_current else (end_str or "Date not verified"),
                "total_months": 0,
                "duration_formatted": "0 months",
                "is_valid": False
            }

        start_idx = ExperienceCalculator.to_month_index(start_ym[0], start_ym[1])
        end_idx = ExperienceCalculator.to_month_index(end_ym[0], end_ym[1])

        # Validate start before end
        if start_idx > end_idx:
            return {
                "start_normalized": f"{start_ym[0]}-{start_ym[1]:02d}",
                "end_normalized": f"{end_ym[0]}-{end_ym[1]:02d}",
                "total_months": 0,
                "duration_formatted": "0 months",
                "is_valid": False
            }

        total_months = max(1, end_idx - start_idx + 1)

        return {
            "start_normalized": f"{start_ym[0]}-{start_ym[1]:02d}",
            "end_normalized": "Present" if is_current else f"{end_ym[0]}-{end_ym[1]:02d}",
            "total_months": total_months,
            "duration_formatted": ExperienceCalculator.format_duration(total_months),
            "is_valid": True
        }

    @staticmethod
    def merge_intervals(intervals: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        if not intervals:
            return []
        intervals.sort(key=lambda x: x[0])
        merged = []
        cs, ce = intervals[0]
        for ns, ne in intervals[1:]:
            if ns <= ce + 1:  # Continuous or overlapping
                ce = max(ce, ne)
            else:
                merged.append((cs, ce))
                cs, ce = ns, ne
        merged.append((cs, ce))
        return merged

    @staticmethod
    def calculate_total_experience_union(positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Deterministic union calculation of non-overlapping experience.
        Filters out invalid or unverified positions before calculating.
        """
        pro_intervals: List[Tuple[int, int, str]] = []
        intern_intervals: List[Tuple[int, int]] = []
        all_intervals: List[Tuple[int, int]] = []
        
        parsed_positions = []
        current_company = None
        current_title = None
        current_start_date = None

        for pos in positions:
            # Check validation
            s_ym, e_ym, is_curr, is_valid = extract_start_end_strings(pos)
            dur_info = ExperienceCalculator.calculate_position_duration(s_ym, e_ym, is_current=is_curr)
            
            comp = str(pos.get("company", "Unknown")).strip()
            title = str(pos.get("title") or pos.get("role", "Role")).strip()
            emp_type = str(pos.get("employment_type", "Full-time")).strip()
            is_internship = "intern" in emp_type.lower() or "intern" in title.lower() or "trainee" in title.lower()

            if dur_info["is_valid"]:
                start_parsed, _ = DateNormalizer.parse_single_date(s_ym)
                end_parsed = (CURRENT_YEAR, CURRENT_MONTH) if is_curr else DateNormalizer.parse_single_date(e_ym)[0]
                
                if start_parsed and end_parsed:
                    s_idx = ExperienceCalculator.to_month_index(start_parsed[0], start_parsed[1])
                    e_idx = ExperienceCalculator.to_month_index(end_parsed[0], end_parsed[1])
                    
                    all_intervals.append((s_idx, e_idx))
                    if is_internship:
                        intern_intervals.append((s_idx, e_idx))
                    else:
                        pro_intervals.append((s_idx, e_idx, comp))

            if is_curr and not current_company:
                current_company = comp
                current_title = title
                current_start_date = dur_info["start_normalized"]

            parsed_positions.append({
                "company": comp,
                "title": title,
                "start_date": dur_info["start_normalized"],
                "end_date": None if is_curr else dur_info["end_normalized"],
                "is_current": is_curr,
                "duration": dur_info["duration_formatted"],
                "duration_months": dur_info["total_months"],
                "employment_type": "Internship" if is_internship else (pos.get("employment_type") or "Full-time"),
                "responsibilities": pos.get("responsibilities", []),
                "technologies": pos.get("technologies", []),
                "source_text": pos.get("source_text") or f"{title} at {comp}",
                "source_section": pos.get("source_section") or "Professional Experience",
                "evidence_status": "VERIFIED" if dur_info["is_valid"] else "UNVERIFIED_EMPLOYMENT"
            })

        # Calculate non-overlapping union durations
        merged_pro = ExperienceCalculator.merge_intervals([(s, e) for s, e, _ in pro_intervals])
        pro_months = sum(e - s + 1 for s, e in merged_pro)

        merged_intern = ExperienceCalculator.merge_intervals(intern_intervals)
        intern_months = sum(e - s + 1 for s, e in merged_intern)

        merged_all = ExperienceCalculator.merge_intervals(all_intervals)
        all_months = sum(e - s + 1 for s, e in merged_all)

        # Detect genuine overlaps between different companies
        overlapping_details = []
        if len(all_intervals) > len(merged_all) and len(pro_intervals) >= 2:
            pro_intervals.sort(key=lambda x: x[0])
            for i in range(len(pro_intervals) - 1):
                if pro_intervals[i][1] >= pro_intervals[i + 1][0] and pro_intervals[i][2].lower() != pro_intervals[i + 1][2].lower():
                    overlapping_details.append(
                        f"Concurrent employment detected between {pro_intervals[i][2]} and {pro_intervals[i+1][2]}."
                    )

        return {
            "total_professional_experience_months": pro_months,
            "total_professional_experience": ExperienceCalculator.format_duration(pro_months),
            "internship_experience_months": intern_months,
            "internship_experience": ExperienceCalculator.format_duration(intern_months),
            "total_experience_including_internships": ExperienceCalculator.format_duration(all_months),
            "current_company": current_company or (parsed_positions[0]["company"] if parsed_positions else "Not specified"),
            "current_title": current_title or (parsed_positions[0]["title"] if parsed_positions else "Not specified"),
            "current_employment_start_date": current_start_date or (parsed_positions[0]["start_date"] if parsed_positions else "Not specified"),
            "employment_history": parsed_positions,
            "has_overlap": len(overlapping_details) > 0,
            "overlapping_details": overlapping_details
        }

    @staticmethod
    def calculate_career_gaps(positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Calculates gaps of 2+ months between consecutive verified positions."""
        intervals = []
        for pos in positions:
            s_ym, e_ym, is_curr, is_valid = extract_start_end_strings(pos)
            if is_valid:
                s_parsed, _ = DateNormalizer.parse_single_date(s_ym)
                e_parsed = (CURRENT_YEAR, CURRENT_MONTH) if is_curr else DateNormalizer.parse_single_date(e_ym)[0]
                if s_parsed and e_parsed:
                    s_idx = ExperienceCalculator.to_month_index(s_parsed[0], s_parsed[1])
                    e_idx = ExperienceCalculator.to_month_index(e_parsed[0], e_parsed[1])
                    intervals.append((s_idx, e_idx, pos.get("company", "Company")))

        if len(intervals) < 2:
            return []

        intervals.sort(key=lambda x: x[0])
        gaps = []

        for i in range(len(intervals) - 1):
            prev_end = intervals[i][1]
            next_start = intervals[i + 1][0]

            gap_months = next_start - prev_end - 1
            if gap_months >= 2:
                prev_year, prev_month = divmod(prev_end, 12)
                next_year, next_month = divmod(next_start, 12)
                
                gaps.append({
                    "gap_months": gap_months,
                    "duration_formatted": ExperienceCalculator.format_duration(gap_months),
                    "between": f"{intervals[i][2]} ({prev_year}-{max(1, prev_month):02d}) and {intervals[i+1][2]} ({next_year}-{max(1, next_month):02d})",
                    "note": f"Unexplained career gap of {ExperienceCalculator.format_duration(gap_months)}."
                })

        return gaps

    @staticmethod
    def calculate_technology_experience(positions: List[Dict[str, Any]], candidate_skills: List[str], raw_text: str = "") -> List[Dict[str, Any]]:
        tech_results = []
        
        for skill in candidate_skills:
            matching_intervals = []
            matching_evidence = []
            skill_lower = skill.lower()
            
            for pos in positions:
                role = pos.get("role") or pos.get("title", "")
                resp = " ".join(pos.get("responsibilities", [])) if isinstance(pos.get("responsibilities"), list) else str(pos.get("responsibilities", ""))
                comp = pos.get("company", "")
                
                combined_pos_text = f"{role} {resp} {comp}".lower()
                
                if skill_lower in combined_pos_text:
                    s_ym, e_ym, is_curr, is_valid = extract_start_end_strings(pos)
                    if is_valid:
                        s_parsed, _ = DateNormalizer.parse_single_date(s_ym)
                        e_parsed = (CURRENT_YEAR, CURRENT_MONTH) if is_curr else DateNormalizer.parse_single_date(e_ym)[0]
                        if s_parsed and e_parsed:
                            s_idx = ExperienceCalculator.to_month_index(s_parsed[0], s_parsed[1])
                            e_idx = ExperienceCalculator.to_month_index(e_parsed[0], e_parsed[1])
                            matching_intervals.append((s_idx, e_idx))
                            matching_evidence.append(f"Used at {comp} ({role})")

            if matching_intervals:
                merged = ExperienceCalculator.merge_intervals(matching_intervals)
                tot_months = sum(e - s + 1 for s, e in merged)
                duration_str = ExperienceCalculator.format_duration(tot_months)
                confidence = "High" if tot_months >= 12 else "Medium"
                evidence_str = "; ".join(matching_evidence)
            else:
                duration_str = "Insufficient evidence"
                confidence = "Low"
                evidence_str = "Skill listed in summary/skills section but no timeline-backed employment evidence found."

            tech_results.append({
                "skill": skill,
                "calculated_experience": duration_str,
                "evidence": evidence_str,
                "confidence": confidence
            })

        return tech_results
