import io
import logging
from typing import Union, BinaryIO
import pypdf

logger = logging.getLogger(__name__)

class PDFExtractionError(Exception):
    """Custom exception raised when PDF extraction fails."""
    pass

class PDFService:
    @staticmethod
    def extract_text_from_bytes(file_bytes: bytes) -> str:
        """
        Extracts plain text from a PDF byte buffer using pypdf.
        """
        if not file_bytes:
            raise PDFExtractionError("Provided PDF file is empty (0 bytes).")
            
        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            text_pages = []
            
            for i, page in enumerate(reader.pages):
                extracted = page.extract_text()
                if extracted:
                    text_pages.append(extracted.strip())
            
            full_text = "\n\n".join(text_pages).strip()
            if not full_text:
                logger.warning("pypdf extracted 0 text characters from PDF. Document might be scanned or image-only.")
                raise PDFExtractionError(
                    "Could not extract readable text from PDF. The document may be scanned images or password protected."
                )
                
            return full_text
            
        except pypdf.errors.PdfReadError as e:
            logger.error(f"pypdf reading error: {e}")
            raise PDFExtractionError(f"Invalid or corrupted PDF file: {str(e)}") from e
        except Exception as e:
            if isinstance(e, PDFExtractionError):
                raise
            logger.error(f"Unexpected error parsing PDF: {e}")
            raise PDFExtractionError(f"Failed to process PDF content: {str(e)}") from e

    @staticmethod
    def extract_text_from_file_path(file_path: str) -> str:
        """
        Extracts text from a local PDF file path.
        """
        with open(file_path, "rb") as f:
            return PDFService.extract_text_from_bytes(f.read())
