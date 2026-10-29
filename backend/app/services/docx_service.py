import io
import logging
import docx

logger = logging.getLogger(__name__)

class DOCXExtractionError(Exception):
    """Raised when DOCX text extraction fails."""
    pass

class DOCXService:
    @staticmethod
    def extract_text_from_bytes(file_bytes: bytes) -> str:
        """
        Extracts plain text from a DOCX file byte stream.
        """
        if not file_bytes:
            raise DOCXExtractionError("Uploaded DOCX file is empty.")
            
        try:
            doc = docx.Document(io.BytesIO(file_bytes))
            paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            full_text = "\n\n".join(paragraphs)
            
            if not full_text:
                raise DOCXExtractionError("Could not extract any readable text from DOCX file.")
                
            return full_text
        except Exception as e:
            logger.error(f"DOCX extraction error: {e}")
            raise DOCXExtractionError(f"Failed to parse DOCX file: {str(e)}") from e
