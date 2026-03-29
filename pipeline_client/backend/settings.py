from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="allow")

    app_name: str = "SmarterVote Pipeline Client"
    artifacts_dir: Path = Path(__file__).resolve().parents[1] / "artifacts"
    storage_mode: str = "local"  # "local" or "gcp"
    gcs_bucket: str | None = None
    firestore_project: str | None = None
    allowed_origins: str = "*"  # comma-separated string — parsed in main.py
    auth0_domain: str | None = None
    auth0_audience: str | None = None

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()
settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
