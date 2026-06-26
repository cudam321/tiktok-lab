from pydantic_settings import BaseSettings
from pathlib import Path

# Resolve .env relative to this file's location (backend/config.py → ../.env)
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    # Zernio
    zernio_api_key: str = ""
    zernio_api_base_url: str = "https://zernio.com/api/v1"

    # AI Agent — set one of these
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    agent_provider: str = "auto"  # "anthropic", "openai", or "auto"

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/tiktok_lab.db"

    # App
    secret_key: str = "change-me-to-a-random-string"

    # Rate limiting (Build plan: 120 req/min)
    zernio_rate_limit: int = 120

    # Paths
    data_dir: Path = Path("data")
    backup_dir: Path = Path("data/backups")
    production_dir: Path = Path("data/productions")
    uploads_dir: Path = Path("data/uploads")

    # OpenMontage — Phase 6 (AI content production) ONLY.
    # Requires a separate, EXTERNAL OpenMontage install (NOT bundled with this repo).
    # Leave unset to disable content production; set OPENMONTAGE_PATH in your .env to the
    # root of your OpenMontage checkout. The Remotion composer is resolved relative to it.
    openmontage_path: Path | None = None

    @property
    def remotion_composer_path(self) -> Path | None:
        """OpenMontage's bundled Remotion composer dir (None when OpenMontage is unset)."""
        if self.openmontage_path is None:
            return None
        return self.openmontage_path / "remotion-composer"

    model_config = {"env_file": str(_ENV_FILE), "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
