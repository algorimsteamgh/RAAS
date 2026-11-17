"""Runtime configuration, read from environment variables.

Names match the ECS task definitions in infra/aws (DATABASE_*, CV_BUCKET,
BATCH_QUEUE_URL, MODEL_BACKEND, BEDROCK_MODEL_ID, SEED_DEMO_DATA).
"""
import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
SEED_DATA_DIR = Path(os.getenv("SEED_DATA_DIR", str(BASE_DIR / "seed_data")))
SAMPLES_DIR = DATA_DIR / "cvs" / "samples"
EXTRACTED_DIR = DATA_DIR / "extracted"

# Ensure directories exist
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)

_LOCAL_ENVS = {"local", "dev", "development", "test"}


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    # local | test | prod
    APP_ENV: str = (_env("APP_ENV") or _env("ENVIRONMENT") or "local").lower()

    # --- PostgreSQL -------------------------------------------------------
    # Either DATABASE_URL (postgresql://user:pass@host:port/db) or the parts
    # below, which is what the ECS task definition passes.
    DATABASE_URL: Optional[str] = _env("DATABASE_URL")
    DATABASE_HOST: str = _env("DATABASE_HOST", "localhost")
    DATABASE_PORT: int = int(_env("DATABASE_PORT", "5432"))
    DATABASE_NAME: str = _env("DATABASE_NAME", "raas")
    DATABASE_USER: str = _env("DATABASE_USER", "postgres")
    DATABASE_PASSWORD: Optional[str] = _env("DATABASE_PASSWORD")
    DATABASE_SSLMODE: str = _env("DATABASE_SSLMODE", "prefer")
    # Optional: the RDS-managed master secret. When set, the password is read
    # from Secrets Manager and re-read after a failed login, so a rotation does
    # not need a task restart.
    DATABASE_SECRET_ARN: Optional[str] = _env("DATABASE_SECRET_ARN")
    DB_POOL_MIN_SIZE: int = int(_env("DB_POOL_MIN_SIZE", "1"))
    DB_POOL_MAX_SIZE: int = int(_env("DB_POOL_MAX_SIZE", "10"))
    DB_CONNECT_TIMEOUT_SECONDS: int = int(_env("DB_CONNECT_TIMEOUT_SECONDS", "10"))
    # Run Alembic migrations when the API starts. Off in production, where the
    # one-off migrate ECS task runs them before a deploy.
    AUTO_MIGRATE: bool = _env_bool("AUTO_MIGRATE", (_env("APP_ENV") or _env("ENVIRONMENT") or "local").lower() in _LOCAL_ENVS)

    # --- Demo data --------------------------------------------------------
    # Seeds the 500 demo candidates and 10 demo jobs into an empty database.
    # Never on in production.
    SEED_DEMO_DATA: bool = _env_bool("SEED_DEMO_DATA", (_env("APP_ENV") or _env("ENVIRONMENT") or "local").lower() in _LOCAL_ENVS)

    # --- AWS ----------------------------------------------------------------
    AWS_REGION: str = _env("AWS_REGION", _env("AWS_DEFAULT_REGION", "ap-southeast-1"))

    # --- CV file storage --------------------------------------------------
    # s3 when CV_BUCKET is set, otherwise a local folder (development, tests).
    STORAGE_BACKEND: str = (_env("STORAGE_BACKEND") or ("s3" if _env("CV_BUCKET") else "local")).lower()
    CV_BUCKET: Optional[str] = _env("CV_BUCKET")
    CV_BUCKET_KMS_KEY_ID: Optional[str] = _env("CV_BUCKET_KMS_KEY_ID")
    CV_LOCAL_DIR: str = _env("CV_LOCAL_DIR", str(BASE_DIR / "data" / "cv_store"))

    # --- Batch processing -------------------------------------------------
    # sqs when BATCH_QUEUE_URL is set (API enqueues, worker processes),
    # otherwise inline (the API process works through the batch itself).
    BATCH_BACKEND: str = (_env("BATCH_BACKEND") or ("sqs" if _env("BATCH_QUEUE_URL") else "inline")).lower()
    BATCH_QUEUE_URL: Optional[str] = _env("BATCH_QUEUE_URL")
    WORKER_CONCURRENCY: int = int(_env("WORKER_CONCURRENCY", "4"))
    WORKER_MAX_ATTEMPTS: int = int(_env("WORKER_MAX_ATTEMPTS", "3"))

    # --- AI model ---------------------------------------------------------
    # bedrock (AWS) | ollama (local development and the Qwen baseline)
    MODEL_BACKEND: str = (_env("MODEL_BACKEND") or "ollama").lower()

    BEDROCK_MODEL_ID: str = _env("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-5")
    # HR chat can use a different model; defaults to BEDROCK_MODEL_ID.
    BEDROCK_CHAT_MODEL_ID: Optional[str] = _env("BEDROCK_CHAT_MODEL_ID")
    BEDROCK_GUARDRAIL_ID: Optional[str] = _env("BEDROCK_GUARDRAIL_ID")
    BEDROCK_GUARDRAIL_VERSION: str = _env("BEDROCK_GUARDRAIL_VERSION", "DRAFT")
    BEDROCK_MAX_TOKENS: int = int(_env("BEDROCK_MAX_TOKENS", "4096"))
    BEDROCK_READ_TIMEOUT_SECONDS: float = float(_env("BEDROCK_READ_TIMEOUT_SECONDS", "50"))
    BEDROCK_CONNECT_TIMEOUT_SECONDS: float = float(_env("BEDROCK_CONNECT_TIMEOUT_SECONDS", "5"))
    BEDROCK_MAX_ATTEMPTS: int = int(_env("BEDROCK_MAX_ATTEMPTS", "4"))

    OLLAMA_BASE_URL: str = _env("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_LLM_MODEL: str = _env("OLLAMA_LLM_MODEL", "qwen2.5:1.5b")
    OLLAMA_EMBEDDING_MODEL: str = _env("OLLAMA_EMBEDDING_MODEL", "mxbai-embed-large:latest")
    OLLAMA_TIMEOUT_SECONDS: float = float(_env("OLLAMA_TIMEOUT_SECONDS", "180.0"))
    OLLAMA_TEMPERATURE: float = 0.0

    @property
    def is_production(self) -> bool:
        return self.APP_ENV in {"prod", "production"}

    @property
    def model_id(self) -> str:
        return self.BEDROCK_MODEL_ID if self.MODEL_BACKEND == "bedrock" else self.OLLAMA_LLM_MODEL


settings = Settings()
