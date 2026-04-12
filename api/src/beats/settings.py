import os
import sys
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Get the api/ directory (parent of src/beats/)
_api_dir = Path(__file__).resolve().parent.parent.parent

# Use .env.test if running tests, else .env
_env_file_name = (
    ".env.test"
    if (
        any("pytest" in arg or "test" in arg for arg in sys.argv)
        or os.getenv("BEATS_TEST_ENV") == "1"
    )
    else ".env"
)
_env_file = _api_dir / _env_file_name


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_env_file, env_file_encoding="utf-8", extra="ignore")

    # Database settings
    db_dsn: str = Field(default="mongodb://localhost:27017", validation_alias="DB_DSN")
    db_name: str = Field(default="ptc", validation_alias="DB_NAME")

    # WebAuthn settings
    webauthn_rp_id: str = Field(default="localhost", validation_alias="WEBAUTHN_RP_ID")
    webauthn_rp_name: str = Field(default="Beats", validation_alias="WEBAUTHN_RP_NAME")
    webauthn_origin: str = Field(
        default="http://localhost:8080", validation_alias="WEBAUTHN_ORIGIN"
    )

    # JWT settings
    jwt_secret: str = Field(default="change-me-in-production", validation_alias="JWT_SECRET")


settings = Settings()
