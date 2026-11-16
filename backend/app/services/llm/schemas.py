"""JSON schemas for tool-use extraction. They mirror the JSON layouts in the
CV and JD system prompts, so every provider returns the same shape.

Kept to the JSON Schema subset all Bedrock models accept (type, properties,
items, required, description; no type unions). Values the document does not
state come back as empty strings and are turned into None by the agents."""

_STR_LIST = {"type": "array", "items": {"type": "string"}}

CV_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Candidate's full name."},
        "current_title": {"type": "string", "description": "Most recent job title."},
        "location": {"type": "string", "description": "City / region / country from the CV header or contact details."},
        "email": {"type": "string", "description": "Email address, or empty string if absent."},
        "phone": {"type": "string", "description": "Phone number, or empty string if absent."},
        "notice_period": {"type": "string", "description": "Notice period as written, or empty string."},
        "employment_history": {
            "type": "array",
            "description": "Every real employment position. Never turn bullet points or technologies into titles or companies.",
            "items": {
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "title": {"type": "string"},
                    "start_date": {"type": "string", "description": "YYYY-MM"},
                    "end_date": {"type": "string", "description": "YYYY-MM, or empty string for the current role."},
                    "is_current": {"type": "boolean"},
                    "employment_type": {"type": "string", "description": "Full-time, Internship or Contract."},
                    "responsibilities": _STR_LIST,
                    "technologies": _STR_LIST,
                },
                "required": ["company", "title", "start_date", "end_date", "is_current"],
            },
        },
        "skills": {**_STR_LIST, "description": "Technical and domain skills that appear in the document."},
        "education": _STR_LIST,
        "certifications": _STR_LIST,
        "projects": _STR_LIST,
        "domains": _STR_LIST,
    },
    "required": ["name", "employment_history", "skills"],
}

JD_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Exact job title."},
        "seniority": {"type": "string", "description": "Junior, Mid-level, Senior, Lead, Staff, Principal, Manager or Director."},
        "department": {"type": "string"},
        "location": {"type": "string"},
        "employment_type": {"type": "string", "description": "Full-time, Part-time, Contract or Remote."},
        "minimum_years_experience": {"type": "number", "description": "Minimum years of experience; '5+ years' is 5."},
        "required_skills": {**_STR_LIST, "description": "Required / must-have skills only."},
        "preferred_skills": {**_STR_LIST, "description": "Preferred / nice-to-have skills."},
        "education_requirements": _STR_LIST,
        "domain_requirements": {**_STR_LIST, "description": "Industry domains."},
        "responsibilities": _STR_LIST,
        "other_constraints": {"type": "string"},
    },
    "required": ["title", "required_skills", "preferred_skills", "minimum_years_experience"],
}

_EMPTY_MARKERS = {"", "null", "none", "n/a", "not specified", "not mentioned"}


def empty_to_none(data: dict, fields: list) -> dict:
    """Turn the empty-string placeholders a schema forces back into None."""
    for field in fields:
        value = data.get(field)
        if isinstance(value, str) and value.strip().lower() in _EMPTY_MARKERS:
            data[field] = None
    return data
