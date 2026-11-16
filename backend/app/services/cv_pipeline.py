"""One CV from bytes to a stored candidate. Shared by POST /api/upload-cv,
the inline batch processor and the SQS worker, so all three behave the same."""
import asyncio
import logging
from typing import Any, Dict, Optional

from backend.app.agents.cv_agent import CVExtractionAgent
from backend.app.db import database as db
from backend.app.services.cv_storage import content_type_for, cv_key, get_cv_storage
from backend.app.services.docx_service import DOCXService
from backend.app.services.pdf_service import PDFService

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = ["pdf", "docx", "txt", "png", "jpg", "jpeg"]
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB, checked by the app (WAF only sees the first 16 KB)

_agent: Optional[CVExtractionAgent] = None


def get_agent() -> CVExtractionAgent:
    global _agent
    if _agent is None:
        _agent = CVExtractionAgent()
    return _agent


def file_extension(filename: Optional[str]) -> str:
    return filename.split(".")[-1].lower() if filename and "." in filename else ""


def extract_text(ext: str, content: bytes) -> str:
    if ext == "pdf":
        return PDFService.extract_text_from_bytes(content)
    if ext == "docx":
        return DOCXService.extract_text_from_bytes(content)
    return content.decode("utf-8", errors="ignore")


async def store_original(candidate_id: str, filename: str, ext: str, sha256_hash: str, content: bytes) -> str:
    """Upload the CV to storage (S3: SSE-KMS + SHA-256 checksum) and record it."""
    key = cv_key(candidate_id, sha256_hash, ext)
    storage = get_cv_storage()
    await asyncio.to_thread(storage.put, key, content, content_type_for(ext), sha256_hash)
    await asyncio.to_thread(db.save_original_file, candidate_id, filename, ext, sha256_hash, key, len(content))
    return key


async def extract_and_save(cv_text: str, candidate_id: str, filename: str, sha256_hash: str) -> Dict[str, Any]:
    candidate = await get_agent().extract_candidate(cv_text, candidate_id=candidate_id)
    cand_dict = candidate.model_dump()
    await asyncio.to_thread(
        db.save_candidate_record, cand_dict, "UPLOADED", "COMPLETED", filename, sha256_hash
    )
    return cand_dict
