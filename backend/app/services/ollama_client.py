"""Ollama provider: local development and the Qwen 2.5 baseline for the
Bedrock model evaluation (MODEL_BACKEND=ollama)."""
import logging
import httpx
from typing import Dict, Any, Optional
from backend.app.config import settings
from backend.app.services.llm.json_utils import clean_and_parse_json, raw_text_snippet  # noqa: F401

logger = logging.getLogger(__name__)

class OllamaClient:
    backend = "ollama"

    def __init__(self, base_url: Optional[str] = None, default_model: Optional[str] = None):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip('/')
        self.default_model = default_model or settings.OLLAMA_LLM_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT_SECONDS

    async def generate_json(self, prompt: str, system_prompt: Optional[str] = None, model: Optional[str] = None,
                            json_schema: Optional[Dict[str, Any]] = None, schema_name: str = "record_extraction") -> Dict[str, Any]:
        """
        Sends a generation request to Ollama and ensures clean JSON output is returned.
        json_schema is accepted for interface parity; the baseline keeps Ollama's
        plain JSON mode so its results stay comparable with the Azure baseline.
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
    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None, model: Optional[str] = None, temperature: Optional[float] = None, use_guardrail: bool = False) -> str:
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
        return clean_and_parse_json(text)

    async def health(self) -> Dict[str, Any]:
        status = "disconnected"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                if res.status_code == 200:
                    names = [m.get("name", "") for m in res.json().get("models", [])]
                    status = "connected" if any(self.default_model in n for n in names) else "connected_model_missing"
        except Exception:
            status = "disconnected"
        return {"status": status, "model": self.default_model, "url": self.base_url}
