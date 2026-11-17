"""Model provider selection (MODEL_BACKEND=bedrock | ollama)."""
import threading
from typing import Optional

from backend.app.config import settings
from backend.app.services.llm.base import LLMClient

_client: Optional[LLMClient] = None
_lock = threading.Lock()


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                if settings.MODEL_BACKEND == "bedrock":
                    from backend.app.services.llm.bedrock_client import BedrockClient

                    _client = BedrockClient()
                else:
                    from backend.app.services.ollama_client import OllamaClient

                    _client = OllamaClient()
    return _client


def set_llm_client(client: Optional[LLMClient]) -> None:
    global _client
    _client = client


__all__ = ["LLMClient", "get_llm_client", "set_llm_client"]
