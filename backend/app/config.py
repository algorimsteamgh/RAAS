import os
from pathlib import Path
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
SEED_DATA_DIR = Path(os.getenv("SEED_DATA_DIR", str(BASE_DIR / "seed_data")))
SAMPLES_DIR = DATA_DIR / "cvs" / "samples"
EXTRACTED_DIR = DATA_DIR / "extracted"

# Ensure directories exist
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)

class Settings(BaseModel):
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_LLM_MODEL: str = os.getenv("OLLAMA_LLM_MODEL", "qwen2.5:1.5b")
    OLLAMA_EMBEDDING_MODEL: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "mxbai-embed-large:latest")
    OLLAMA_TIMEOUT_SECONDS: float = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180.0"))
    OLLAMA_TEMPERATURE: float = 0.0

settings = Settings()
