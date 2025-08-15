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
    allowed_origins: list[str] = Field(default_factory=lambda: ["*"])

    class Config:
        env_prefix = ""
        env_file = ".env"
        extra = "allow"


settings = Settings()
settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
