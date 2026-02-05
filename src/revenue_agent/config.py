"""Configuration settings for the Revenue Leakage Agent."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Find the project root (where .env lives)
# config.py -> revenue_agent -> src -> tt-ai (project root)
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenAI settings
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # Data paths (relative to project root)
    data_dir: Path = _PROJECT_ROOT / "data"
    sandbox_dir: Path = _PROJECT_ROOT / "data" / "sandbox"

    # API settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    @property
    def billing_plans_path(self) -> Path:
        return self.data_dir / "billing_plans.json"

    @property
    def invoices_path(self) -> Path:
        return self.data_dir / "invoices.json"

    @property
    def credit_memos_path(self) -> Path:
        return self.data_dir / "credit_memos.json"

    @property
    def exchange_rates_path(self) -> Path:
        return self.data_dir / "exchange_rates.json"

    @property
    def audit_log_path(self) -> Path:
        return self.sandbox_dir / "audit_log.json"


settings = Settings()
