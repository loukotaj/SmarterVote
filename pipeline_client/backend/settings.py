from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="allow")

    app_name: str = "SmarterVote Pipeline Client"
    artifacts_dir: Path = Path(__file__).resolve().parents[1] / "artifacts"
    storage_mode: str = "local"  # "local" or "gcp"
    gcs_bucket: str | None = None
    firestore_project: str | None = None
    allowed_origins: list[str] = Field(default_factory=lambda: ["*"])
    auth0_domain: str | None = None
    auth0_audience: str | None = None

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


settings = Settings()
settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
