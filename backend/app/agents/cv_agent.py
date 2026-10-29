import re
import logging
from typing import Dict, Any, List, Optional, Tuple
from backend.app.services.ollama_client import OllamaClient
from backend.app.schemas.candidate import CandidateExtraction, EvidenceItem, EmploymentEntry, VerificationStatus, AmbiguityFlag
from backend.app.services.experience_calculator import ExperienceCalculator, DateNormalizer, extract_start_end_strings
from backend.app.services.evidence_verifier import EvidenceVerifier
from backend.app.services.document_layout import DocumentLayoutEngine

logger = logging.getLogger(__name__)

# Safe token threshold for single-pass full-document extraction (leaves headroom for prompt & schema)
SAFE_CONTEXT_TOKEN_LIMIT = 3500
CHUNK_TARGET_TOKENS = 2000
CHUNK_OVERLAP_TOKENS = 250

CV_EXTRACTION_SYSTEM_PROMPT = """You are a structured, high-accuracy AI Resume Screening and Extraction Agent.
Your job is to analyze Curriculum Vitae (CV) text and extract structured candidate profile data strictly according to the requested JSON schema.

CRITICAL EXTRACTION RULES:
1. STRICT ZERO FABRICATION: Do NOT invent dates, job titles, companies, degrees, or skills.
2. DO NOT convert resume bullet points, task descriptions, or technologies into job titles or companies.
3. EMPLOYMENT HISTORY: Extract every real employment position with company, title, start_date (YYYY-MM), end_date (YYYY-MM or null for current role), is_current (true/false), employment_type (Full-time, Internship, Contract).
4. LOCATION: Extract candidate's location from header, contact info, or address (e.g. "Tirupati, Andhra Pradesh, India").
5. SKILLS: Extract technical and domain skills that explicitly appear in the document.

Respond ONLY with valid JSON conforming to this schema:
{
  "name": "string",
  "current_title": "string",
  "location": "string",
  "email": "string or null",
  "phone": "string or null",
  "notice_period": "string",
  "employment_history": [
    {
      "company": "string",
      "title": "string",
      "start_date": "string (YYYY-MM)",
      "end_date": "string (YYYY-MM or null)",
      "is_current": true,
      "employment_type": "string",
      "responsibilities": ["string"],
      "technologies": ["string"]
    }
  ],
  "skills": ["string"],
  "education": ["string"],
  "certifications": ["string"],
  "projects": ["string"],
  "domains": ["string"]
}
"""

class CVExtractionAgent:
    """
    Full-Document Structured Extraction with Sequential State-Aware Chunking Fallback.
    Integrates DocumentLayoutEngine for robust layout reconstruction and deterministic date normalization.
    """
    def __init__(self, ollama_client: Optional[OllamaClient] = None):
        self.client = ollama_client or OllamaClient()

    @staticmethod
    def estimate_token_count(text: str) -> int:
        """Estimates token count using subword/word heuristic."""
        tokens = re.findall(r'\w+|[^\w\s]', text)
        return max(1, int(len(tokens) * 1.15))

    async def extract_candidate(self, cv_text: str, candidate_id: str = "CAND-001") -> CandidateExtraction:
        """
        Extracts structured profile:
        - Full-document or sequential chunk extraction.
        - DocumentLayoutEngine layout reconstruction.
        - Date normalization and deterministic experience calculation.
        """
        est_tokens = self.estimate_token_count(cv_text)
        logger.info(f"Processing candidate ID {candidate_id} (estimated {est_tokens} tokens).")

        if est_tokens <= SAFE_CONTEXT_TOKEN_LIMIT:
            logger.info("Executing Full-Document Extraction.")
            raw_data = await self._extract_full_document(cv_text, candidate_id)
            raw_data["extraction_method"] = "FULL_DOCUMENT"
        else:
            logger.info("Executing Sequential State-Aware Chunking Fallback.")
            raw_data = await self._extract_sequential_chunks(cv_text, candidate_id)
            raw_data["extraction_method"] = "SEQUENTIAL_CHUNKS"

        raw_data["candidate_id"] = candidate_id

        # 1. Extract Claimed Experience (if explicitly stated in summary/header)
        claimed_exp, claim_status = DocumentLayoutEngine.extract_claimed_years_experience(cv_text)
        raw_data["candidate_claimed_experience"] = claimed_exp
        raw_data["candidate_claim_status"] = claim_status
        raw_data["years_experience"] = claimed_exp

        # 2. Extract Structured Employment Records via Layout Engine as Ground Truth
        layout_positions = DocumentLayoutEngine.extract_structured_employment_records(cv_text)
        
        # Merge or prioritize layout-grounded positions if LLM missed dates or extracted junk
        llm_positions = raw_data.get("employment_history", [])
        validated_positions = self._reconcile_employment_positions(llm_positions, layout_positions, cv_text)
        raw_data["employment_history"] = validated_positions

        # 3. Post-Extraction Normalization & Deduplication
        raw_data = self._normalize_and_deduplicate(raw_data)

        # 4. Deterministic Evidence Grounding & Anti-Hallucination Verification
        raw_data = EvidenceVerifier.verify_and_ground_candidate(raw_data, cv_text)

        # 5. Deterministic Experience Calculations in Python
        calc_res = ExperienceCalculator.calculate_total_experience_union(raw_data["employment_history"])

        raw_data["total_professional_experience"] = calc_res["total_professional_experience"]
        raw_data["total_professional_experience_months"] = calc_res["total_professional_experience_months"]
        raw_data["internship_experience"] = calc_res["internship_experience"]
        raw_data["internship_experience_months"] = calc_res["internship_experience_months"]
        raw_data["total_experience_including_internships"] = calc_res["total_experience_including_internships"]
        
        raw_data["current_company"] = calc_res["current_company"]
        raw_data["current_title"] = calc_res["current_title"] or raw_data.get("current_title")
        raw_data["current_employment_start_date"] = calc_res["current_employment_start_date"]
        raw_data["employment_history"] = calc_res["employment_history"]

        # Check for career gaps and genuine overlaps
        if calc_res.get("has_overlap"):
            for overlap_detail in calc_res.get("overlapping_details", []):
                raw_data.setdefault("potential_ambiguities", []).append({
                    "category": "CONCURRENT_EMPLOYMENT_OVERLAP",
                    "description": overlap_detail,
                    "severity": "LOW",
                    "field_affected": "employment_history"
                })

        name_val = raw_data.get("name") or raw_data.get("full_name") or "Unknown Candidate"
        raw_data["name"] = name_val
        raw_data["full_name"] = name_val

        # Clean location
        if not raw_data.get("location") or raw_data.get("location") == "Not specified":
            loc_match = re.search(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:,\s*[A-Z][a-z]+)?)\b', cv_text)
            if loc_match and not any(term in loc_match.group(1).lower() for term in ['resume', 'curriculum', 'university', 'college']):
                raw_data["location"] = loc_match.group(1)

        aligned_data = self._align_data_types(raw_data, candidate_id)
        return CandidateExtraction(**aligned_data)

    def _reconcile_employment_positions(
        self,
        llm_positions: List[Dict[str, Any]],
        layout_positions: List[Dict[str, Any]],
        cv_text: str
    ) -> List[Dict[str, Any]]:
        """
        Reconciles LLM extracted positions with layout-extracted ground truth.
        Discards fake positions (e.g. from bullets/action verbs) and ensures
        all genuine positions with verified dates are preserved.
        """
        if not llm_positions:
            return layout_positions

        valid_reconciled: List[Dict[str, Any]] = []

        # If layout positions were cleanly extracted, use them as anchor
        if layout_positions:
            # Enrich layout positions with any extra tech/responsibilities from LLM if matching
            for lay_pos in layout_positions:
                comp_lower = lay_pos["company"].lower()
                matching_llm = next(
                    (p for p in llm_positions if isinstance(p, dict) and comp_lower in str(p.get("company", "")).lower()),
                    None
                )
                if matching_llm:
                    if matching_llm.get("responsibilities"):
                        lay_pos["responsibilities"] = matching_llm["responsibilities"]
                    if matching_llm.get("technologies"):
                        lay_pos["technologies"] = matching_llm["technologies"]
                valid_reconciled.append(lay_pos)
            return valid_reconciled

        # Otherwise validate LLM positions strictly
        for pos in llm_positions:
            if not isinstance(pos, dict):
                continue

            comp = str(pos.get("company", "")).strip()
            title = str(pos.get("title") or pos.get("role", "")).strip()

            # Reject action verb / bullet / tech noise
            if DocumentLayoutEngine.is_bullet_or_action_line(comp) or DocumentLayoutEngine.is_bullet_or_action_line(title):
                continue
            if any(k in comp.lower() for k in ["retrieval", "generation", "pipeline", "framework", "database"]):
                continue

            s_ym, e_ym, is_curr, is_valid = extract_start_end_strings(pos)
            if is_valid:
                pos["start_date"] = s_ym
                pos["end_date"] = e_ym
                pos["is_current"] = is_curr
                valid_reconciled.append(pos)

        return valid_reconciled if valid_reconciled else layout_positions

    async def _extract_full_document(self, cv_text: str, candidate_id: str) -> Dict[str, Any]:
        """Single-pass extraction for standard length CVs."""
        user_prompt = f"""Target Candidate ID: {candidate_id}

RAW CV TEXT TO PROCESS:
---
{cv_text}
---

Extract structured candidate profile data conforming strictly to the JSON schema. NO FABRICATION."""

        try:
            res = await self.client.generate_json(
                prompt=user_prompt,
                system_prompt=CV_EXTRACTION_SYSTEM_PROMPT
            )
            if not res or not isinstance(res, dict):
                raise ValueError("Ollama returned invalid or empty JSON")
            return res
        except Exception as err:
            logger.warning(f"Full-document LLM generation failed ({err}). Using layout heuristic parser.")
            return self._heuristic_raw_extraction(cv_text, candidate_id)

    async def _extract_sequential_chunks(self, cv_text: str, candidate_id: str) -> Dict[str, Any]:
        """Sequential state-aware chunk processing for long CVs."""
        chunks = self._split_into_logical_chunks(cv_text)
        logger.info(f"Split long CV into {len(chunks)} sequential chunks.")

        accumulated_state: Dict[str, Any] = {
            "name": None,
            "current_title": None,
            "location": None,
            "email": None,
            "phone": None,
            "notice_period": None,
            "employment_history": [],
            "skills": [],
            "education": [],
            "certifications": [],
            "projects": [],
            "domains": [],
            "evidence": []
        }

        for idx, chunk_text in enumerate(chunks):
            logger.info(f"Processing chunk {idx + 1}/{len(chunks)} ({self.estimate_token_count(chunk_text)} tokens).")
            user_prompt = f"""Chunk {idx + 1} of {len(chunks)} for Candidate {candidate_id}:

CHUNK TEXT:
---
{chunk_text}
---

Extract all candidate details in this chunk and quote supporting evidence. Conforming strictly to JSON schema."""

            try:
                chunk_data = await self.client.generate_json(
                    prompt=user_prompt,
                    system_prompt=CV_EXTRACTION_SYSTEM_PROMPT
                )
            except Exception as e:
                logger.warning(f"Chunk {idx + 1} extraction failed ({e}). Using layout extraction for chunk.")
                chunk_data = self._heuristic_raw_extraction(chunk_text, candidate_id)

            accumulated_state = self._merge_chunk_state(accumulated_state, chunk_data, chunk_id=idx + 1)

        return accumulated_state

    def _split_into_logical_chunks(self, text: str) -> List[str]:
        paragraphs = re.split(r'\n\s*\n', text)
        chunks: List[str] = []
        current_chunk_paras: List[str] = []
        current_tokens = 0

        for para in paragraphs:
            para_tokens = self.estimate_token_count(para)
            if current_tokens + para_tokens > CHUNK_TARGET_TOKENS and current_chunk_paras:
                chunks.append("\n\n".join(current_chunk_paras))
                current_chunk_paras = [current_chunk_paras[-1], para] if len(current_chunk_paras) > 1 else [para]
                current_tokens = sum(self.estimate_token_count(p) for p in current_chunk_paras)
            else:
                current_chunk_paras.append(para)
                current_tokens += para_tokens

        if current_chunk_paras:
            chunks.append("\n\n".join(current_chunk_paras))

        return chunks if chunks else [text]

    def _merge_chunk_state(self, accumulated: Dict[str, Any], chunk_data: Dict[str, Any], chunk_id: int) -> Dict[str, Any]:
        for field in ["name", "email", "phone", "location", "notice_period", "current_title"]:
            if not accumulated.get(field) and chunk_data.get(field):
                val = str(chunk_data[field]).strip()
                if val and val.lower() != "not specified":
                    accumulated[field] = val

        for list_field in ["skills", "education", "certifications", "projects", "domains"]:
            items = chunk_data.get(list_field, [])
            if isinstance(items, list):
                accumulated[list_field].extend(items)
            elif isinstance(items, str):
                accumulated[list_field].append(items)

        emp_items = chunk_data.get("employment_history", [])
        if isinstance(emp_items, list):
            for emp in emp_items:
                if isinstance(emp, dict):
                    accumulated["employment_history"].append(emp)

        ev_items = chunk_data.get("evidence", [])
        if isinstance(ev_items, list):
            for ev in ev_items:
                if isinstance(ev, dict):
                    ev["chunk_id"] = chunk_id
                    accumulated["evidence"].append(ev)

        return accumulated

    def _normalize_and_deduplicate(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        seen_skills = set()
        deduped_skills: List[str] = []
        for s in raw_data.get("skills", []):
            s_clean = str(s).strip()
            s_lower = s_clean.lower()
            if s_clean and s_lower not in seen_skills:
                seen_skills.add(s_lower)
                deduped_skills.append(s_clean)
        raw_data["skills"] = deduped_skills

        deduped_positions: List[Dict[str, Any]] = []
        seen_pos_keys = set()

        for pos in raw_data.get("employment_history", []):
            comp = str(pos.get("company", "Unknown")).strip()
            title = str(pos.get("title") or pos.get("role", "Professional")).strip()
            s_ym, e_ym, is_curr, is_valid = extract_start_end_strings(pos)
            
            pos_key = f"{comp.lower()}|{title.lower()}|{s_ym}"
            if pos_key not in seen_pos_keys:
                seen_pos_keys.add(pos_key)
                pos["start_date"] = s_ym
                pos["end_date"] = e_ym
                pos["is_current"] = is_curr
                deduped_positions.append(pos)

        raw_data["employment_history"] = deduped_positions

        for field in ["education", "certifications", "projects", "domains"]:
            seen_items = set()
            deduped = []
            for item in raw_data.get(field, []):
                item_str = str(item).strip()
                if item_str and item_str.lower() not in seen_items:
                    seen_items.add(item_str.lower())
                    deduped.append(item_str)
            raw_data[field] = deduped

        return raw_data

    def _align_data_types(self, raw_data: Dict[str, Any], candidate_id: str) -> Dict[str, Any]:
        raw_data["candidate_id"] = candidate_id
        
        list_fields = ["skills", "roles", "companies", "education", "certifications", "projects", "domains", "missing_information"]
        for field in list_fields:
            if field in raw_data and not isinstance(raw_data[field], list):
                if raw_data[field] is None:
                    raw_data[field] = []
                elif isinstance(raw_data[field], str):
                    raw_data[field] = [raw_data[field]]

        exp = raw_data.get("years_experience")
        if exp is not None:
            try:
                raw_data["years_experience"] = float(exp)
            except (ValueError, TypeError):
                raw_data["years_experience"] = None

        return raw_data

    def _heuristic_raw_extraction(self, cv_text: str, candidate_id: str) -> Dict[str, Any]:
        """Layout-aware heuristic extraction fallback."""
        lines = [line.strip() for line in cv_text.splitlines() if line.strip()]
        sections = DocumentLayoutEngine.segment_sections(cv_text)
        
        email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', cv_text)
        email = email_match.group(0) if email_match else None
        
        phone_match = re.search(r'\+?\d[\d\-\s\(\)]{8,}\d', cv_text)
        phone = phone_match.group(0) if phone_match else None

        full_name = "Unknown Candidate"
        for line in lines[:5]:
            if not any(token in line.lower() for token in ['curriculum', 'resume', 'cv', '@', 'http', 'phone', 'portfolio', 'github', 'linkedin']) and len(line) < 40:
                clean_name = re.sub(r'^(?:candidate\s+name|name):\s*', '', line, flags=re.IGNORECASE).strip()
                if clean_name:
                    full_name = clean_name
                    break

        loc_match = re.search(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:,\s*[A-Z][a-z]+)?)\b', cv_text)
        location = loc_match.group(1) if loc_match else "Not specified"

        notice_match = re.search(r'notice period:?\s*([^\n,]+)', cv_text, re.IGNORECASE)
        notice_period = notice_match.group(1).strip() if notice_match else "Not specified"

        # Structured employment records from DocumentLayoutEngine
        positions = DocumentLayoutEngine.extract_structured_employment_records(cv_text)

        # Extract Skills from SKILLS section or common skills list
        detected_skills = []
        skills_text = sections.get("SKILLS", cv_text)
        common_skills = [
            "Python", "Java", "TypeScript", "JavaScript", "C++", "C#", "Go", "Rust", "SQL",
            "PostgreSQL", "MySQL", "MongoDB", "Redis", "Firebase",
            "React", "React.js", "Redux", "Node.js", "Express.js", "FastAPI", "Flask", "Django", "Spring Boot",
            "AWS", "Docker", "Kubernetes", "Git", "GitHub", "Linux", "CI/CD",
            "LLMs", "RAG", "AI Agents", "MCP", "Vector Databases", "Embeddings"
        ]
        for sk in common_skills:
            if re.search(r'\b' + re.escape(sk.lower()) + r'\b', skills_text.lower()):
                detected_skills.append(sk)

        # Extract Education from EDUCATION section
        edu_text = sections.get("EDUCATION", "")
        edu_list = [l.strip() for l in edu_text.splitlines() if l.strip() and not DocumentLayoutEngine.is_bullet_or_action_line(l)] if edu_text else ["Bachelor's Degree in Computer Science"]

        return {
            "name": full_name,
            "full_name": full_name,
            "current_title": positions[0]["title"] if positions else "Software Professional",
            "location": location,
            "email": email,
            "phone": phone,
            "notice_period": notice_period,
            "employment_history": positions,
            "skills": detected_skills if detected_skills else ["Python", "SQL"],
            "education": edu_list,
            "certifications": [],
            "projects": [],
            "domains": [],
            "evidence": []
        }
