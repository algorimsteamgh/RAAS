"""Model provider interface used by the agents (CV extraction, JD extraction,
HR chat). Implementations: BedrockClient (AWS) and OllamaClient (local
development and the Qwen baseline)."""
from typing import Any, Dict, Optional, Protocol


class LLMClient(Protocol):
    backend: str
    default_model: str

    async def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        json_schema: Optional[Dict[str, Any]] = None,
        schema_name: str = "record_extraction",
    ) -> Dict[str, Any]:
        """Return one JSON object. With json_schema, providers that support
        tool use constrain the output to that schema."""
        ...

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        use_guardrail: bool = False,
    ) -> str:
        ...

    async def health(self) -> Dict[str, Any]:
        """{"status": "connected" | "connected_model_missing" | "disconnected", "model": ...}"""
        ...
