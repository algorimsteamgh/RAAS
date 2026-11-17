"""Amazon Bedrock provider (Converse API).

* CV and JD extraction use tool use with a JSON schema per extractor, so the
  model returns a structured object instead of free text that needs repair.
* Temperature 0 for extraction. The HR chat can run behind a Bedrock
  Guardrail (BEDROCK_GUARDRAIL_ID).
* botocore adaptive retries back off on ThrottlingException; every call has
  connect and read timeouts. Token counts and latency are logged per call,
  never prompt or response text (CVs are personal data).
* boto3 is synchronous: calls run in a worker thread so the event loop keeps
  serving other requests.
"""
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from backend.app.config import settings
from backend.app.services.llm.json_utils import clean_and_parse_json

logger = logging.getLogger(__name__)

_HEALTH_TTL_SECONDS = 300


class BedrockError(RuntimeError):
    pass


def _error_code(err: Exception) -> str:
    response = getattr(err, "response", None) or {}
    return response.get("Error", {}).get("Code", "")


class BedrockClient:
    backend = "bedrock"

    def __init__(self, model_id: Optional[str] = None, chat_model_id: Optional[str] = None, client: Any = None):
        self.default_model = model_id or settings.BEDROCK_MODEL_ID
        self.chat_model = chat_model_id or settings.BEDROCK_CHAT_MODEL_ID or self.default_model
        if client is None:
            import boto3
            from botocore.config import Config

            client = boto3.client(
                "bedrock-runtime",
                region_name=settings.AWS_REGION,
                config=Config(
                    retries={"max_attempts": settings.BEDROCK_MAX_ATTEMPTS, "mode": "adaptive"},
                    connect_timeout=settings.BEDROCK_CONNECT_TIMEOUT_SECONDS,
                    read_timeout=settings.BEDROCK_READ_TIMEOUT_SECONDS,
                ),
            )
        self.client = client
        self._health_cache: Optional[Dict[str, Any]] = None
        self._health_checked_at = 0.0

    # ------------------------------------------------------------------ calls
    def _converse(self, request: Dict[str, Any], purpose: str) -> Dict[str, Any]:
        started = time.monotonic()
        try:
            response = self.client.converse(**request)
        except Exception as err:
            logger.warning(
                "bedrock.converse failed purpose=%s model=%s code=%s latency_ms=%d",
                purpose, request.get("modelId"), _error_code(err) or type(err).__name__,
                int((time.monotonic() - started) * 1000),
            )
            raise
        usage = response.get("usage", {})
        logger.info(
            "bedrock.converse purpose=%s model=%s input_tokens=%s output_tokens=%s latency_ms=%s stop_reason=%s",
            purpose, request.get("modelId"), usage.get("inputTokens"), usage.get("outputTokens"),
            response.get("metrics", {}).get("latencyMs", int((time.monotonic() - started) * 1000)),
            response.get("stopReason"),
        )
        return response

    @staticmethod
    def _base_request(model: str, prompt: str, system_prompt: Optional[str], temperature: float, max_tokens: int) -> Dict[str, Any]:
        request: Dict[str, Any] = {
            "modelId": model,
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"temperature": temperature, "maxTokens": max_tokens},
        }
        if system_prompt:
            request["system"] = [{"text": system_prompt}]
        return request

    @staticmethod
    def _content_blocks(response: Dict[str, Any]) -> List[Dict[str, Any]]:
        return response.get("output", {}).get("message", {}).get("content", []) or []

    def _text(self, response: Dict[str, Any]) -> str:
        return "".join(block.get("text", "") for block in self._content_blocks(response)).strip()

    def _converse_with_tool(self, request: Dict[str, Any], tool_name: str, purpose: str) -> Dict[str, Any]:
        """Force the extraction tool. Some models accept only `any` or no
        toolChoice at all; fall back in that order."""
        choices = [{"tool": {"name": tool_name}}, {"any": {}}, None]
        last_err: Optional[Exception] = None
        for choice in choices:
            attempt = dict(request)
            attempt["toolConfig"] = dict(request["toolConfig"])
            if choice is None:
                attempt["toolConfig"].pop("toolChoice", None)
            else:
                attempt["toolConfig"]["toolChoice"] = choice
            try:
                return self._converse(attempt, purpose)
            except Exception as err:
                if _error_code(err) == "ValidationException" and "tool" in str(err).lower():
                    last_err = err
                    continue
                raise
        raise BedrockError(f"Model rejected tool use: {last_err}")

    # --------------------------------------------------------------- interface
    async def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        json_schema: Optional[Dict[str, Any]] = None,
        schema_name: str = "record_extraction",
    ) -> Dict[str, Any]:
        request = self._base_request(model or self.default_model, prompt, system_prompt, 0.0, settings.BEDROCK_MAX_TOKENS)
        if not json_schema:
            response = await asyncio.to_thread(self._converse, request, "json")
            return clean_and_parse_json(self._text(response))

        request["toolConfig"] = {
            "tools": [{
                "toolSpec": {
                    "name": schema_name,
                    "description": "Record the structured data extracted from the document.",
                    "inputSchema": {"json": json_schema},
                }
            }],
            "toolChoice": {"tool": {"name": schema_name}},
        }
        response = await asyncio.to_thread(self._converse_with_tool, request, schema_name, schema_name)
        if response.get("stopReason") == "max_tokens":
            raise BedrockError("Model output was cut off at maxTokens; raise BEDROCK_MAX_TOKENS")
        for block in self._content_blocks(response):
            tool_use = block.get("toolUse")
            if tool_use and tool_use.get("name") == schema_name and isinstance(tool_use.get("input"), dict):
                return tool_use["input"]
        # No tool call (model answered in text): parse it as JSON.
        return clean_and_parse_json(self._text(response))

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        use_guardrail: bool = False,
    ) -> str:
        request = self._base_request(
            model or self.chat_model, prompt, system_prompt,
            0.3 if temperature is None else temperature, min(settings.BEDROCK_MAX_TOKENS, 2048),
        )
        if use_guardrail and settings.BEDROCK_GUARDRAIL_ID:
            request["guardrailConfig"] = {
                "guardrailIdentifier": settings.BEDROCK_GUARDRAIL_ID,
                "guardrailVersion": settings.BEDROCK_GUARDRAIL_VERSION,
                "trace": "disabled",
            }
        response = await asyncio.to_thread(self._converse, request, "chat")
        if response.get("stopReason") == "guardrail_intervened":
            logger.warning("bedrock guardrail intervened on an HR chat message")
        return self._text(response)

    async def health(self) -> Dict[str, Any]:
        """Reachability of the configured model, cached for five minutes (a
        one-token Converse call; Bedrock has no free ping)."""
        now = time.monotonic()
        if self._health_cache and now - self._health_checked_at < _HEALTH_TTL_SECONDS:
            return self._health_cache
        request = self._base_request(self.default_model, "ping", None, 0.0, 1)
        try:
            await asyncio.to_thread(self._converse, request, "health")
            status = "connected"
        except Exception as err:
            code = _error_code(err)
            status = "connected_model_missing" if code in {"AccessDeniedException", "ResourceNotFoundException", "ValidationException"} else "disconnected"
        self._health_cache = {"status": status, "model": self.default_model}
        self._health_checked_at = now
        return self._health_cache
