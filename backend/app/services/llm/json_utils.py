"""Parsing of model output that should be JSON (text responses only; tool-use
responses are already structured)."""
import json
import logging
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)


def raw_text_snippet(text: str, max_length: int = 200) -> str:
    return text[:max_length] + "..." if len(text) > max_length else text


def clean_and_parse_json(text: str) -> Dict[str, Any]:
    """Strip code fences and surrounding prose, then parse the JSON object."""
    text = (text or "").strip()

    if "```" in text:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            text = match.group(1)
        else:
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            text = text.strip()

    start_idx = text.find("{")
    end_idx = text.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        text = text[start_idx:end_idx + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse JSON directly from model response: {e}. Attempting basic sanitization.")
        text_repaired = re.sub(r",\s*([\]}])", r"\1", text)
        try:
            return json.loads(text_repaired)
        except json.JSONDecodeError as err:
            raise ValueError(f"Model output could not be parsed as valid JSON: {raw_text_snippet(text)}") from err
