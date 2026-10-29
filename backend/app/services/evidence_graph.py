import logging
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class EvidenceType(str, Enum):
    EMPLOYMENT = "EMPLOYMENT"
    PROJECT = "PROJECT"
    EDUCATION = "EDUCATION"
    CERTIFICATION = "CERTIFICATION"
    SKILLS_SECTION = "SKILLS_SECTION"
    SUMMARY = "SUMMARY"
    OTHER = "OTHER"

class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"

class EvidenceNode(BaseModel):
    id: str = Field(..., description="Unique evidence node ID")
    candidate_id: str = Field(..., description="Candidate ID")
    claim: str = Field(..., description="Statement or claim e.g. 'Candidate has React experience'")
    skill: Optional[str] = Field(default=None, description="Associated skill or technology")
    evidence_type: EvidenceType = Field(default=EvidenceType.EMPLOYMENT)
    company: Optional[str] = Field(default=None, description="Company name if employment-backed")
    project: Optional[str] = Field(default=None, description="Project name if project-backed")
    start_date: Optional[str] = Field(default=None, description="Start date YYYY-MM")
    end_date: Optional[str] = Field(default=None, description="End date YYYY-MM or PRESENT")
    source_text: str = Field(..., description="Direct quote or snippet from CV document")
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.HIGH)

class SkillEvidenceGraph(BaseModel):
    skill: str
    total_calculated_duration: str = "0 months"
    total_months: int = 0
    confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    evidence_nodes: List[EvidenceNode] = Field(default_factory=list)
    reasoning: str = ""

class EvidenceGraphEngine:
    @staticmethod
    def build_candidate_evidence_graph(candidate_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Builds an Evidence Knowledge Graph linking Candidate -> Skill -> Evidence -> Source -> Time Period -> Confidence.
        """
        cand_id = candidate_data.get("candidate_id", "CAND-001")
        skills = candidate_data.get("skills", [])
        positions = candidate_data.get("employment_history", [])
        projects = candidate_data.get("projects", [])
        certifications = candidate_data.get("certifications", [])
        evidence_quotes = candidate_data.get("evidence", [])

        graph_nodes: List[EvidenceNode] = []
        skill_graphs: Dict[str, SkillEvidenceGraph] = {}

        # 1. Process Employment Evidence
        for idx, pos in enumerate(positions):
            comp = pos.get("company", "Unknown")
            role = pos.get("title") or pos.get("role", "Role")
            s_date = pos.get("start_date", "")
            e_date = pos.get("end_date", "PRESENT")
            resp_list = pos.get("responsibilities", [])
            resp_text = " ".join(resp_list) if isinstance(resp_list, list) else str(resp_list)
            tech_list = pos.get("technologies", [])

            pos_text = f"{role} at {comp}. {resp_text}".strip()

            for sk in skills:
                sk_lower = sk.lower()
                used_in_resp = sk_lower in pos_text.lower()
                used_in_tech = any(sk_lower == t.lower() for t in tech_list)

                if used_in_resp or used_in_tech:
                    node_id = f"ev_emp_{idx}_{sk.replace(' ', '_')}"
                    source = f"Used {sk} during employment as {role} at {comp} ({s_date} - {e_date})."
                    if resp_text:
                        source = f"\"{resp_text[:120]}...\" (Section: Experience at {comp})"

                    ev_node = EvidenceNode(
                        id=node_id,
                        candidate_id=cand_id,
                        claim=f"Candidate has verified employment experience with {sk}",
                        skill=sk,
                        evidence_type=EvidenceType.EMPLOYMENT,
                        company=comp,
                        start_date=s_date,
                        end_date=e_date,
                        source_text=source,
                        confidence=ConfidenceLevel.HIGH
                    )
                    graph_nodes.append(ev_node)

        # 2. Process Project Evidence
        for idx, proj in enumerate(projects):
            proj_str = str(proj)
            for sk in skills:
                if sk.lower() in proj_str.lower():
                    node_id = f"ev_proj_{idx}_{sk.replace(' ', '_')}"
                    ev_node = EvidenceNode(
                        id=node_id,
                        candidate_id=cand_id,
                        claim=f"Candidate implemented project using {sk}",
                        skill=sk,
                        evidence_type=EvidenceType.PROJECT,
                        project=proj_str[:40],
                        source_text=f"Project: {proj_str[:120]}",
                        confidence=ConfidenceLevel.MEDIUM
                    )
                    graph_nodes.append(ev_node)

        # 3. Process Skills Section & Certifications
        for sk in skills:
            matching_nodes = [n for n in graph_nodes if n.skill and n.skill.lower() == sk.lower()]
            
            if not matching_nodes:
                # Skill present only in Skills section without timeline evidence
                node_id = f"ev_skillsec_{sk.replace(' ', '_')}"
                ev_node = EvidenceNode(
                    id=node_id,
                    candidate_id=cand_id,
                    claim=f"Skill {sk} listed in skills section",
                    skill=sk,
                    evidence_type=EvidenceType.SKILLS_SECTION,
                    source_text=f"Listed under skills section in resume",
                    confidence=ConfidenceLevel.LOW
                )
                graph_nodes.append(ev_node)
                matching_nodes.append(ev_node)

            # Determine aggregate confidence for skill
            high_conf = any(n.confidence == ConfidenceLevel.HIGH for n in matching_nodes)
            med_conf = any(n.confidence == ConfidenceLevel.MEDIUM for n in matching_nodes)
            
            if high_conf:
                aggregate_conf = ConfidenceLevel.HIGH
                reason = f"Explicitly verified through production employment evidence."
            elif med_conf:
                aggregate_conf = ConfidenceLevel.MEDIUM
                reason = f"Mentioned in projects / qualifications without explicit employment duration."
            else:
                aggregate_conf = ConfidenceLevel.LOW
                reason = f"Listed in skills section only; insufficient timeline-backed employment evidence."

            skill_graphs[sk] = SkillEvidenceGraph(
                skill=sk,
                total_calculated_duration=candidate_data.get("total_professional_experience", "0 months") if high_conf else "Insufficient evidence",
                confidence=aggregate_conf,
                evidence_nodes=matching_nodes,
                reasoning=reason
            )

        return {
            "candidate_id": cand_id,
            "all_evidence_nodes": [n.model_dump() for n in graph_nodes],
            "skill_graphs": {k: v.model_dump() for k, v in skill_graphs.items()}
        }
