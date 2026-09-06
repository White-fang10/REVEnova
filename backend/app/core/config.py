"""REVEnova application configuration.

Central place for all environment-driven settings. Sensible defaults are
provided so the application runs out-of-the-box with zero configuration
(SQLite + deterministic mock AI + synchronous job execution).
"""
import os
from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    app_name: str = "REVEnova"
    app_version: str = "1.0.0"

    # --- Database ---
    # When USE_POSTGRES is true AND a reachable DATABASE_URL is provided, the
    # app uses PostgreSQL (with pgvector). Otherwise it falls back to SQLite,
    # which requires no external infrastructure.
    use_postgres: bool = False
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/revenova"
    sqlite_path: str = str(DATA_DIR / "revenova.db")

    # --- LLM ---
    # If an OPENAI_API_KEY is provided the app uses the real LLM for reasoning
    # (diagnosis / strategy generation / messaging ONLY). Otherwise it uses a
    # deterministic mock that reproduces rule-based reasoning so the demo still
    # works without any external dependency. Money math is ALWAYS deterministic.
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    use_mock_llm: bool = True  # overridden automatically if key present

    # --- Background jobs ---
    # Celery/Redis are optional. When unavailable, jobs execute synchronously
    # so nothing is blocked. Set to true when a broker is present.
    use_celery: bool = False

    # --- Policy constants (deterministic, never LLM-driven) ---
    human_approval_threshold: float = 100_000.0      # ₹ > this amount -> human approval
    max_auto_retries: int = 2                        # max automatic retries
    max_discount_pct: float = 10.0                   # max discount without approval
    max_contacts_7d: int = 3                         # max contacts in 7 days
    max_consecutive_failures: int = 3                # stopping rule
    min_recovery_probability: float = 0.10           # below this -> stop automated recovery

    # --- Mock LLM behavior ---
    mock_llm_seed: int = 42

    # CORS - allow the Next.js dev server
    cors_origins: list = ["http://localhost:3000", "http://127.0.0.1:3000"]

    class Config:
        env_file = str(BASE_DIR / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

# Automatically resolve the LLM backend from the presence of an API key.
if settings.openai_api_key:
    settings.use_mock_llm = False
