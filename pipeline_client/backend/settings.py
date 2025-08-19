from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "SmarterVote Pipeline Client"
    artifacts_dir: Path = Path(__file__).resolve().parents[1] / "artifacts"
    skip_llm_apis: bool = False
    skip_external_apis: bool = False
    skip_network_calls: bool = False
    skip_cloud_services: bool = False
    storage_mode: str = "local"  # "local" or "gcp"
    gcs_bucket: str | None = None
    firestore_project: str | None = None
    allowed_origins: list[str] = Field(default_factory=lambda: ["*"])
    auth0_domain: str | None = None
    auth0_audience: str | None = None

    class Config:
        env_prefix = ""
        env_file = ".env"
        extra = "allow"


settings = Settings()
settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
