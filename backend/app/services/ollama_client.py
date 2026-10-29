import json
import re
import logging
import httpx
from typing import Dict, Any, Optional
from backend.app.config import settings

logger = logging.getLogger(__name__)

class OllamaClient:
    def __init__(self, base_url: str = settings.OLLAMA_BASE_URL, default_model: str = settings.OLLAMA_LLM_MODEL):
        self.base_url = base_url.rstrip('/')
        self.default_model = default_model
        self.timeout = settings.OLLAMA_TIMEOUT_SECONDS

    async def generate_json(self, prompt: str, system_prompt: Optional[str] = None, model: Optional[str] = None) -> Dict[str, Any]:
        """
        Sends a generation request to Ollama and ensures clean JSON output is returned.
        """
        target_model = model or self.default_model
        endpoint = f"{self.base_url}/api/generate"

        payload = {
            "model": target_model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": settings.OLLAMA_TEMPERATURE,
                "num_predict": 1024,
                "num_thread": 2
            }
        }

        if system_prompt:
            payload["system"] = system_prompt

        timeout_cfg = httpx.Timeout(self.timeout, connect=2.0)
        async with httpx.AsyncClient(timeout=timeout_cfg) as client:
            try:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
                data = response.json()
                raw_response = data.get("response", "")
                
                return self._clean_and_parse_json(raw_response)
            except httpx.HTTPStatusError as e:
                logger.error(f"Ollama API HTTP error {e.response.status_code}: {e.response.text}")
                raise RuntimeError(f"Ollama API error: {e.response.status_code}") from e
            except httpx.RequestError as e:
                logger.error(f"Failed to connect to Ollama service at {self.base_url}: {e}")
                raise RuntimeError(f"Cannot connect to Ollama at {self.base_url}. Ensure 'ollama serve' is running.") from e
    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None, model: Optional[str] = None, temperature: Optional[float] = None) -> str:
        """
        Sends a generation request to Ollama and returns natural language text response.
        """
        target_model = model or self.default_model
        endpoint = f"{self.base_url}/api/generate"

        payload = {
            "model": target_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature if temperature is not None else 0.3,
                "num_predict": 1024,
                "num_thread": 2
            }
        }

        if system_prompt:
            payload["system"] = system_prompt

        timeout_cfg = httpx.Timeout(self.timeout, connect=2.0)
        async with httpx.AsyncClient(timeout=timeout_cfg) as client:
            try:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("response", "").strip()
            except httpx.HTTPStatusError as e:
                logger.error(f"Ollama API HTTP error {e.response.status_code}: {e.response.text}")
                raise RuntimeError(f"Ollama API error: {e.response.status_code}") from e
            except httpx.RequestError as e:
                logger.error(f"Failed to connect to Ollama service at {self.base_url}: {e}")
                raise RuntimeError(f"Cannot connect to Ollama at {self.base_url}. Ensure 'ollama serve' is running.") from e

    def _clean_and_parse_json(self, text: str) -> Dict[str, Any]:
        """
        Cleans markdown codeblocks, leading/trailing whitespace, and parses JSON string.
        """
        text = text.strip()
        
        # Remove ```json ... ``` codeblock wrappers if present
        if "```" in text:
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
            if match:
                text = match.group(1)
            else:
                # Strip leading/trailing codeblocks manually
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
                text = text.strip()

        # Find first '{' and last '}'
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            text = text[start_idx:end_idx + 1]

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON directly from model response: {e}. Attempting basic sanitization.")
            # Basic repair for trailing commas or unescaped quotes
            text_repaired = re.sub(r",\s*([\]}])", r"\1", text)
            try:
                return json.loads(text_repaired)
            except json.JSONDecodeError as err:
                raise ValueError(f"Model output could not be parsed as valid JSON: {raw_text_snippet(text)}") from err

def raw_text_snippet(text: str, max_length: int = 200) -> str:
    return text[:max_length] + "..." if len(text) > max_length else text
