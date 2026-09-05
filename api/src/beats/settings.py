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

    # ------------------------------------------------------------------
    # home.space SSO (optional second front door)
    #
    # Beats keeps its own email + passkey login exactly as it is. These
    # settings add a SECOND way in, for the `home.space` stack this
    # instance is deployed into: the `auth` issuer at auth.home.space
    # mints an Ed25519 `Home-Session` cookie scoped to `.home.space`,
    # which every sibling vhost -- including this one -- receives.
    #
    # Default OFF. Beats on Cloud Run, or on `localhost:7999` with no
    # issuer running, behaves precisely as it did before: /api/auth/sso/*
    # reports disabled and nothing else changes.
    # ------------------------------------------------------------------
    sso_enabled: bool = Field(default=False, validation_alias="BEATS_SSO_ENABLED")

    # The issuer DID we require in the `iss` claim. Not a URL: the home
    # stack identifies its issuer as a did:web, and the DID is what is
    # actually signed into the token.
    sso_issuer: str = Field(default="did:web:auth.home.space", validation_alias="BEATS_SSO_ISSUER")

    # Where THIS PROCESS reaches the issuer -- loopback inside the home
    # stack, so introspection never leaves the machine and never depends
    # on DNS, the ingress or TLS being healthy.
    sso_auth_base_url: str = Field(
        default="http://127.0.0.1:6007", validation_alias="BEATS_SSO_AUTH_BASE_URL"
    )

    # Where the BROWSER is sent to obtain a session. Empty means "derive
    # it from the request's own Host", which is what makes one build work
    # unchanged on beats.home.space, beats.<lan-ip>.nip.io and
    # beats.home.elghareeb.space -- the same three-name problem the auth
    # service solves dynamically in its own cookie-domain logic.
    sso_login_url: str = Field(default="", validation_alias="BEATS_SSO_LOGIN_URL")

    sso_cookie_name: str = Field(default="Home-Session", validation_alias="BEATS_SSO_COOKIE_NAME")
    sso_provider_name: str = Field(default="home.space", validation_alias="BEATS_SSO_PROVIDER_NAME")

    # Roles allowed to CREATE a beats account on first SSO login. Any
    # role may still link to an account that already exists -- this gates
    # provisioning only. `just invite "Visitor" guest 60` deliberately
    # does not leave a permanent user record behind.
    sso_provision_roles: str = Field(
        default="owner,admin", validation_alias="BEATS_SSO_PROVISION_ROLES"
    )

    # How long a fetched JWKS is trusted before refetching. The cached
    # copy is kept indefinitely past this as an offline fallback.
    sso_jwks_ttl_seconds: int = Field(default=300, validation_alias="BEATS_SSO_JWKS_TTL_SECONDS")

    # Timeout for issuer introspection. Loopback, so this is generous;
    # exceeding it falls back to offline signature verification rather
    # than failing the login.
    sso_issuer_timeout_seconds: float = Field(
        default=2.0, validation_alias="BEATS_SSO_ISSUER_TIMEOUT_SECONDS"
    )

    @property
    def sso_provision_role_set(self) -> frozenset[str]:
        """Roles permitted to auto-provision, lowercased. Empty means any."""
        return frozenset(
            r.strip().lower() for r in self.sso_provision_roles.split(",") if r.strip()
        )

    # AI Coach (Stage 2)
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    coach_model: str = Field(default="claude-sonnet-4-6", validation_alias="COACH_MODEL")
    coach_monthly_budget_usd: float = Field(
        default=10.0, validation_alias="COACH_MONTHLY_BUDGET_USD"
    )


settings = Settings()
