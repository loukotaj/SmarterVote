import os

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

    @property
    def is_cloud_run(self) -> bool:
        return bool(os.getenv("K_SERVICE") or os.getenv("CLOUD_RUN_SERVICE"))

    def validate_cloud_config(self) -> None:
        """Fail fast if running on Cloud Run without required cloud backends.

        This prevents silent fallback to ephemeral local storage.
        """
        if not self.is_cloud_run:
            return
        errors = []
        if not self.gcs_bucket:
            errors.append("GCS_BUCKET is required on Cloud Run (set via Terraform/deploy script)")
        if not self.firestore_project:
            errors.append("FIRESTORE_PROJECT is required on Cloud Run (set via Terraform/deploy script)")
        if self.storage_mode != "gcp":
            errors.append(f"STORAGE_MODE must be 'gcp' on Cloud Run, got '{self.storage_mode}'")
        if errors:
            raise RuntimeError(
                "Cloud Run environment detected but cloud backends are not configured:\n  - "
                + "\n  - ".join(errors)
            )


settings = Settings()
settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
# Blow up immediately if deployed without required cloud config
settings.validate_cloud_config()
