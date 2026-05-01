import os
import sys
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# RFC 7518 §3.2 requires at least 32 bytes for HS256 HMAC keys.
# Anything shorter is rejected: pyjwt logs InsecureKeyLengthWarning,
# but more importantly an attacker who can guess or brute-force a
# short shared secret can mint arbitrary session tokens for any user.
JWT_SECRET_MIN_BYTES = 32

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
    db_name: str = Field(default="beats", validation_alias="DB_NAME")

    # WebAuthn settings
    webauthn_rp_id: str = Field(default="localhost", validation_alias="WEBAUTHN_RP_ID")
    webauthn_rp_name: str = Field(default="Beats", validation_alias="WEBAUTHN_RP_NAME")
    webauthn_origin: str = Field(
        default="http://localhost:8080", validation_alias="WEBAUTHN_ORIGIN"
    )

    # JWT settings
    jwt_secret: str = Field(validation_alias="JWT_SECRET")

    @field_validator("jwt_secret")
    @classmethod
    def _validate_jwt_secret_length(cls, v: str) -> str:
        """JWT_SECRET must be at least 32 bytes (RFC 7518 §3.2 for
        HS256). A shorter secret lets an attacker who can guess
        or brute-force the shared key mint session tokens for
        any user. Generate one with: `openssl rand -base64 48`."""
        if len(v.encode("utf-8")) < JWT_SECRET_MIN_BYTES:
            raise ValueError(
                f"JWT_SECRET must be at least {JWT_SECRET_MIN_BYTES} bytes "
                f"(got {len(v.encode('utf-8'))}). "
                "Generate one with: openssl rand -base64 48"
            )
        return v

    # Google Calendar OAuth (optional)
    google_client_id: str = Field(default="", validation_alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(default="", validation_alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = Field(
        default="http://localhost:8080/settings?calendar=callback",
        validation_alias="GOOGLE_REDIRECT_URI",
    )

    # GitHub OAuth (optional)
    github_client_id: str = Field(default="", validation_alias="GITHUB_CLIENT_ID")
    github_client_secret: str = Field(default="", validation_alias="GITHUB_CLIENT_SECRET")
    github_redirect_uri: str = Field(
        default="http://localhost:8080/settings?github=callback",
        validation_alias="GITHUB_REDIRECT_URI",
    )

    # Fitbit OAuth (optional)
    fitbit_client_id: str = Field(default="", validation_alias="FITBIT_CLIENT_ID")
    fitbit_client_secret: str = Field(default="", validation_alias="FITBIT_CLIENT_SECRET")
    fitbit_redirect_uri: str = Field(
        default="http://localhost:8080/settings?fitbit=callback",
        validation_alias="FITBIT_REDIRECT_URI",
    )

    # AI Coach (Stage 2)
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    coach_model: str = Field(default="claude-sonnet-4-6", validation_alias="COACH_MODEL")
    coach_monthly_budget_usd: float = Field(
        default=10.0, validation_alias="COACH_MONTHLY_BUDGET_USD"
    )


settings = Settings()
