from enum import Enum
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field, ConfigDict

class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    INFERRED = "INFERRED"

class EvidenceItem(BaseModel):
    attribute: str = Field(..., description="The attribute name e.g. 'years_experience', 'skills:Python'")
    source_section: str = Field(default="Body", description="The section of the CV where this was found e.g. 'Experience', 'Education'")
    source_text: str = Field(..., description="Direct quote or sentence snippet supporting the extracted information")
    verification_status: VerificationStatus = Field(default=VerificationStatus.VERIFIED, description="Whether snippet was verified in source text")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Calibrated confidence score from 0.0 to 1.0")
    char_offset_start: Optional[int] = Field(default=None, description="Start character index in source CV text")
    char_offset_end: Optional[int] = Field(default=None, description="End character index in source CV text")
    chunk_id: Optional[int] = Field(default=None, description="Sequential chunk index if multi-chunk parsed")

class AmbiguityFlag(BaseModel):
    category: str = Field(..., description="Category of ambiguity e.g. 'OVERLAPPING_ROLES', 'UNVERIFIED_DATES', 'CAREER_GAP'")
    description: str = Field(..., description="Human-readable explanation of ambiguity for recruiter review")
    severity: str = Field(default="MEDIUM", description="Severity level: LOW, MEDIUM, HIGH")
    field_affected: Optional[str] = Field(default=None, description="Field affected by this ambiguity")

class EmploymentEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    employment_id: Optional[str] = Field(default=None, description="Unique identifier for employment record")
    company: str = Field(..., description="Company or organization name")
    title: str = Field(..., description="Job title or role")
    start_date: Optional[str] = Field(default=None, description="Normalized start date in YYYY-MM format")
    end_date: Optional[str] = Field(default=None, description="Normalized end date in YYYY-MM format, or None if currently employed")
    is_current: bool = Field(default=False, description="True if currently employed here (Present/Current)")
    duration: Optional[str] = Field(default="0 months", description="Calculated duration string e.g. '2 years 2 months'")
    duration_months: Optional[int] = Field(default=0, description="Calculated total months")
    employment_type: Optional[str] = Field(default="Full-time", description="Full-time, Contract, Internship, Freelance")
    responsibilities: List[str] = Field(default_factory=list, description="Key responsibilities and achievements")
    technologies: List[str] = Field(default_factory=list, description="Technologies used in this position")
    source_text: Optional[str] = Field(default=None, description="Source snippet supporting this position")
    source_section: Optional[str] = Field(default="Professional Experience", description="Source section name")
    evidence_status: str = Field(default="VERIFIED", description="VERIFIED, UNVERIFIED_EMPLOYMENT, AMBIGUOUS")
    is_verified: bool = Field(default=True, description="Whether employment entry exists in source text")

class CandidateExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidate_id: str = Field(..., description="Unique identifier for candidate")
    name: Optional[str] = Field(default=None, description="Candidate's full name")
    full_name: Optional[str] = Field(default=None, description="Candidate's full name (alias)")
    
    current_title: Optional[str] = Field(default=None, description="Current or most recent job title")
    location: Optional[str] = Field(default=None, description="Location extracted from header, contact info, or address")
    email: Optional[str] = Field(default=None, description="Candidate email address")
    phone: Optional[str] = Field(default=None, description="Candidate phone number")
    
    candidate_claimed_experience: Optional[float] = Field(default=None, description="Explicitly claimed years of experience in summary if stated, else None")
    candidate_claim_status: str = Field(default="NOT_STATED", description="EXPLICITLY_CLAIMED or NOT_STATED")
    years_experience: Optional[float] = Field(default=None, description="Years of experience float (None if not explicitly stated)")
    
    total_professional_experience: Optional[str] = Field(default="0 months", description="Formatted total professional experience string")
    total_professional_experience_months: int = Field(default=0, description="Calculated non-overlapping total professional experience in months")
    
    internship_experience: Optional[str] = Field(default="0 months", description="Formatted internship experience duration")
    internship_experience_months: int = Field(default=0, description="Calculated non-overlapping internship experience in months")
    
    total_experience_including_internships: Optional[str] = Field(default="0 months", description="Formatted total experience including internships")
    
    current_company: Optional[str] = Field(default=None, description="Company name of current employment (ending in Present/Current)")
    current_employment_start_date: Optional[str] = Field(default=None, description="Start date of current employment")
    
    notice_period: Optional[str] = Field(default="Not specified", description="Explicit notice period or availability if present in CV")
    
    employment_history: List[EmploymentEntry] = Field(default_factory=list, description="Extracted professional employment history entries")
    
    skills: List[str] = Field(default_factory=list, description="Extracted technical and professional skills")
    roles: List[str] = Field(default_factory=list, description="Job titles or roles held")
    companies: List[str] = Field(default_factory=list, description="Companies or organizations worked for")
    education: List[str] = Field(default_factory=list, description="Degrees, diplomas, and academic institutions")
    certifications: List[str] = Field(default_factory=list, description="Professional certifications and credentials")
    projects: List[str] = Field(default_factory=list, description="Key projects worked on with brief tech context")
    domains: List[str] = Field(default_factory=list, description="Industry domains e.g. FinTech, E-commerce, Healthcare")
    
    evidence: List[EvidenceItem] = Field(default_factory=list, description="Direct text quotes backing up major extracted facts")
    confidence: Dict[str, float] = Field(default_factory=dict, description="Calibrated extraction confidence per field (0.0 to 1.0)")
    missing_information: List[str] = Field(default_factory=list, description="Explicit list of missing or ambiguous details in CV")
    potential_ambiguities: List[AmbiguityFlag] = Field(default_factory=list, description="Ambiguities or anomalies flagged for recruiter review")
    extraction_method: str = Field(default="FULL_DOCUMENT", description="FULL_DOCUMENT or SEQUENTIAL_CHUNKS")

class RequirementEvaluation(BaseModel):
    requirement: str
    category: str = "REQUIRED_SKILL"  # EXPERIENCE, REQUIRED_SKILL, PREFERRED_SKILL, EDUCATION
    calculated_experience: Optional[str] = "Insufficient evidence"
    status: str = "FAIL"  # PASS, PARTIAL, FAIL
    confidence: str = "LOW"  # HIGH, MEDIUM, LOW
    evidence_summary: str = ""
    verification_status: VerificationStatus = VerificationStatus.VERIFIED

class EvaluationReport(BaseModel):
    candidate_id: str
    candidate_name: str
    job_id: Optional[str] = None
    job_title: Optional[str] = None
    status: str = "PARTIAL"  # PASS, PARTIAL, FAIL
    overall_score: float = 0.0  # 0.0 - 100.0
    recommendation: str = "REVIEW"  # SHORTLIST, REVIEW, DO_NOT_SHORTLIST
    calibrated_confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    
    total_professional_experience: str = "0 months"
    claimed_experience: str = "Not explicitly claimed"
    calculated_experience: str = "0 months"
    experience_discrepancy: str = "None"
    
    employment_timeline: List[Dict[str, Any]] = Field(default_factory=list)
    matched_requirements: List[RequirementEvaluation] = Field(default_factory=list)
    partial_matches: List[RequirementEvaluation] = Field(default_factory=list)
    missing_requirements: List[RequirementEvaluation] = Field(default_factory=list)
    
    potential_ambiguities: List[AmbiguityFlag] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    potential_concerns: List[str] = Field(default_factory=list)
    qualitative_reasoning: str = ""
    final_recommendation: str = ""
    calculation_notes: str = ""
