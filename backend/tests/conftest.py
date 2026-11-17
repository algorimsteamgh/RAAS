"""Test setup: every test runs against PostgreSQL.

Set TEST_DATABASE_URL (default postgresql://postgres@localhost:5432/raas_test).
The schema is rebuilt from the Alembic migrations once per session (downgrade
to base, then upgrade, which also tests the downgrade path) and the demo data
is seeded. CV files go to a temporary folder; the model backend is an
unreachable Ollama, so the agents use their deterministic fallbacks unless a
test injects a client.
"""
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("APP_ENV", "test")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres@localhost:5432/raas_test")
os.environ.setdefault("CV_LOCAL_DIR", tempfile.mkdtemp(prefix="raas-cv-"))
os.environ["STORAGE_BACKEND"] = "local"
os.environ["BATCH_BACKEND"] = "inline"
os.environ["MODEL_BACKEND"] = "ollama"
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:9"
os.environ["OLLAMA_TIMEOUT_SECONDS"] = "2"
os.environ["AUTO_MIGRATE"] = "false"
os.environ["SEED_DEMO_DATA"] = "true"

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def database():
    from alembic import command

    from backend.app.db import database as db
    from backend.app.db.migrate import alembic_config

    cfg = alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    from backend.app.main import seed_demo_data

    seed_demo_data()
    yield
    db.close_pool()
