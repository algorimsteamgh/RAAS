import re
import logging
from typing import Dict, Any, List, Tuple, Optional
from backend.app.schemas.candidate import EvidenceItem, VerificationStatus, AmbiguityFlag

logger = logging.getLogger(__name__)

class EvidenceVerifier:
    """
    Deterministic string and token-level verification engine.
    Ensures the LLM is NEVER treated as the single source of truth for evidence.
    Verifies that extracted claims and quotes genuinely exist in the source CV text.
    """

    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """Collapses consecutive whitespace and trims string."""
        return re.sub(r'\s+', ' ', text).strip()

    @classmethod
    def locate_snippet_in_text(cls, snippet: str, raw_text: str) -> Tuple[bool, Optional[int], Optional[int]]:
        """
        Deterministically finds if a snippet exists in the raw CV text.
        Returns: (found: bool, start_idx: Optional[int], end_idx: Optional[int])
        """
        if not snippet or not raw_text:
            return False, None, None

        snippet_clean = snippet.strip().strip('"\'')
        if not snippet_clean:
            return False, None, None

        # 1. Exact match
        pos = raw_text.find(snippet_clean)
        if pos != -1:
            return True, pos, pos + len(snippet_clean)

        # 2. Case-insensitive match
        pos_lower = raw_text.lower().find(snippet_clean.lower())
        if pos_lower != -1:
            return True, pos_lower, pos_lower + len(snippet_clean)

        # 3. Normalized whitespace match
        norm_raw = cls.normalize_whitespace(raw_text)
        norm_snippet = cls.normalize_whitespace(snippet_clean)
        pos_norm = norm_raw.lower().find(norm_snippet.lower())
        if pos_norm != -1:
            # Map back approximately to character index in raw_text
            # Try to match the first 20 chars
            head_snippet = norm_snippet[:min(25, len(norm_snippet))]
            head_pos = raw_text.lower().find(head_snippet.lower())
            if head_pos != -1:
                return True, head_pos, head_pos + len(snippet_clean)
            return True, None, None

        # 4. Token Subsequence Match (first 4 and last 4 words)
        words = [w for w in re.split(r'\s+', snippet_clean) if len(w) > 2]
        if len(words) >= 4:
            pattern = re.escape(words[0]) + r'.{1,100}' + re.escape(words[-1])
            m = re.search(pattern, raw_text, re.IGNORECASE | re.DOTALL)
            if m:
                return True, m.start(), m.end()

        # 5. Short keyword check if snippet is short (single skill / role)
        if len(words) <= 3 and len(snippet_clean) < 40:
            pattern = r'\b' + re.escape(snippet_clean) + r'\b'
            m = re.search(pattern, raw_text, re.IGNORECASE)
            if m:
                return True, m.start(), m.end()

        return False, None, None

    @classmethod
    def verify_and_ground_candidate(
        cls,
        candidate_data: Dict[str, Any],
        raw_cv_text: str,
        chunk_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Validates all claims, skills, employment entries, and evidence items
        against the source document text. Strips or marks unverified hallucinations.
        """
        verified_evidence: List[Dict[str, Any]] = []
        ambiguities: List[Dict[str, Any]] = []

        # 1. Verify and ground explicit evidence items
        raw_evidence_list = candidate_data.get("evidence", [])
        verified_count = 0
        total_claims_count = 0

        for item in raw_evidence_list:
            if isinstance(item, dict):
                attr = item.get("attribute", "General")
                source_txt = item.get("source_text", "")
                section = item.get("source_section", "Body")
            else:
                attr = getattr(item, "attribute", "General")
                source_txt = getattr(item, "source_text", "")
                section = getattr(item, "source_section", "Body")

            total_claims_count += 1
            is_found, start_idx, end_idx = cls.locate_snippet_in_text(source_txt, raw_cv_text)

            status = VerificationStatus.VERIFIED if is_found else VerificationStatus.UNVERIFIED
            conf = 1.0 if is_found else 0.3
            if is_found:
                verified_count += 1
            else:
                ambiguities.append({
                    "category": "UNVERIFIED_EVIDENCE_QUOTE",
                    "description": f"Extracted quote for '{attr}' could not be located in source text.",
                    "severity": "LOW",
                    "field_affected": attr
                })

            verified_evidence.append({
                "attribute": attr,
                "source_section": section,
                "source_text": source_txt,
                "verification_status": status.value,
                "confidence": conf,
                "char_offset_start": start_idx,
                "char_offset_end": end_idx,
                "chunk_id": chunk_id
            })

        # 2. Verify Skills Against Source Text (Anti-Hallucination)
        extracted_skills = candidate_data.get("skills", [])
        grounded_skills: List[str] = []
        raw_lower = raw_cv_text.lower()

        for skill in extracted_skills:
            skill_clean = str(skill).strip()
            if not skill_clean:
                continue

            # Check if skill literally appears in raw CV text (word boundary or substring)
            skill_pattern = r'\b' + re.escape(skill_clean.lower()) + r'\b'
            skill_found = bool(re.search(skill_pattern, raw_lower)) or (skill_clean.lower() in raw_lower)

            if skill_found:
                grounded_skills.append(skill_clean)
                # Create an evidence item if not already captured
                has_ev = any(e.get("attribute") == f"skills:{skill_clean}" for e in verified_evidence)
                if not has_ev:
                    is_f, s_idx, e_idx = cls.locate_snippet_in_text(skill_clean, raw_cv_text)
                    verified_evidence.append({
                        "attribute": f"skills:{skill_clean}",
                        "source_section": "Skills/Experience",
                        "source_text": f"Found skill '{skill_clean}' in CV",
                        "verification_status": VerificationStatus.VERIFIED.value,
                        "confidence": 1.0,
                        "char_offset_start": s_idx,
                        "char_offset_end": e_idx,
                        "chunk_id": chunk_id
                    })
            else:
                # Flag hallucinated skill
                ambiguities.append({
                    "category": "HALLUCINATED_SKILL",
                    "description": f"Extracted skill '{skill_clean}' was not found in raw CV text.",
                    "severity": "HIGH",
                    "field_affected": "skills"
                })
                verified_evidence.append({
                    "attribute": f"skills:{skill_clean}",
                    "source_section": "Unverified Extraction",
                    "source_text": f"Skill '{skill_clean}' absent from CV text",
                    "verification_status": VerificationStatus.UNVERIFIED.value,
                    "confidence": 0.0,
                    "char_offset_start": None,
                    "char_offset_end": None,
                    "chunk_id": chunk_id
                })

        candidate_data["skills"] = grounded_skills

        # 3. Verify Employment History Positions Against Text
        emp_history = candidate_data.get("employment_history", [])
        verified_emp = []
        for pos in emp_history:
            comp = pos.get("company", "Unknown")
            title = pos.get("title") or pos.get("role", "Role")
            comp_found, s_idx, e_idx = cls.locate_snippet_in_text(comp, raw_cv_text)
            
            pos_copy = dict(pos)
            pos_copy["is_verified"] = comp_found
            if comp_found:
                pos_copy["source_evidence"] = f"Verified role '{title}' at '{comp}' in CV text."
            else:
                pos_copy["source_evidence"] = f"Unverified: Company '{comp}' not found in document text."
                ambiguities.append({
                    "category": "UNVERIFIED_EMPLOYMENT_ENTRY",
                    "description": f"Company '{comp}' could not be verified in the raw CV text.",
                    "severity": "MEDIUM",
                    "field_affected": "employment_history"
                })
            verified_emp.append(pos_copy)

        candidate_data["employment_history"] = verified_emp
        candidate_data["evidence"] = verified_evidence

        # 4. Merge existing ambiguities if present
        existing_amb = candidate_data.get("potential_ambiguities", [])
        all_ambiguities = existing_amb + ambiguities
        candidate_data["potential_ambiguities"] = all_ambiguities

        # 5. Compute Calibrated Extraction Confidence
        total_items = max(1, len(grounded_skills) + len(verified_emp) + total_claims_count)
        verified_items = (
            len(grounded_skills) +
            len([p for p in verified_emp if p.get("is_verified")]) +
            verified_count
        )
        evidence_coverage = min(1.0, verified_items / total_items)
        ambiguity_penalty = min(0.30, len(ambiguities) * 0.05)
        
        calibrated_conf = round(max(0.2, min(1.0, evidence_coverage - ambiguity_penalty)), 2)

        conf_dict = candidate_data.get("confidence", {})
        conf_dict["overall"] = calibrated_conf
        conf_dict["skills"] = round(len(grounded_skills) / max(1, len(extracted_skills)), 2) if extracted_skills else 1.0
        conf_dict["evidence_coverage"] = round(evidence_coverage, 2)
        candidate_data["confidence"] = conf_dict

        return candidate_data
