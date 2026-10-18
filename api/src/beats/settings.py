import os
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from beats.brand import APP_NAME

# RFC 7518 §3.2 requires at least 32 bytes for HS256 HMAC keys.
# Anything shorter is rejected: pyjwt logs InsecureKeyLengthWarning,
# but more importantly an attacker who can guess or brute-force a
# short shared secret can mint arbitrary session tokens for any user.
JWT_SECRET_MIN_BYTES = 32
# The report-link key is held to the same floor: an HMAC key shorter than
# the hash's output (32 bytes for SHA-256) weakens it (RFC 2104 §3).
REPORT_LINK_KEY_MIN_BYTES = 32

_api_dir = Path(__file__).resolve().parent.parent.parent

# Which env file to load, named explicitly. conftest.py points this at
# .env.test before any test module imports this one. It used to be inferred by
# scanning sys.argv for the substring "test", which meant any argument that
# happened to contain it — a path, a module name, a --latest flag — silently
# swung the whole application onto test configuration.
_env_file = _api_dir / os.getenv("BEATS_ENV_FILE", ".env")


def _require_https(url: str, what: str) -> None:
    """HTTPS, except on this machine: a code or a client secret sent in the
    clear can be read by anyone on the path, and a local IdP for development
    has no certificate."""
    parsed = urlparse(url)
    local = parsed.hostname in ("localhost", "127.0.0.1")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        raise ValueError(f"{what} must be an https:// URL (http:// only for localhost): {url}")


class OIDCProviderSettings(BaseModel):
    """One OpenID Connect provider people can sign in with."""

    # Names the provider in URLs and on a linked identity. Changing it later
    # leaves existing links working (they are keyed on issuer and subject)
    # but listed under the old id until the next sign-in through it.
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,31}$")
    # On the button: "Continue with <name>".
    name: str = Field(min_length=1)
    # Exactly as the provider's discovery document states it; the ID token's
    # `iss` must equal it.
    issuer: str
    client_id: str = Field(min_length=1)
    # Empty for a public client. PKCE protects the code either way; a
    # confidential client adds the secret on top.
    client_secret: str = ""
    scopes: str = "openid email profile"
    # Whether someone the provider vouches for, but who has no account here
    # yet, gets one. Off unless named: a provider like Google vouches for
    # everyone with an account there, which is rarely who should get in.
    allow_signup: bool = False

    @field_validator("issuer")
    @classmethod
    def _issuer_https(cls, v: str) -> str:
        _require_https(v, "issuer")
        return v.rstrip("/")

    @field_validator("scopes")
    @classmethod
    def _scopes_openid(cls, v: str) -> str:
        if "openid" not in v.split():
            raise ValueError("scopes must include openid")
        return v


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_env_file, env_file_encoding="utf-8", extra="ignore")

    # Database settings
    db_dsn: str = Field(default="mongodb://localhost:27017", validation_alias="DB_DSN")
    db_name: str = Field(default="beats", validation_alias="DB_NAME")

    # WebAuthn settings
    webauthn_rp_id: str = Field(default="localhost", validation_alias="WEBAUTHN_RP_ID")
    # Display only: the browser shows it in the passkey prompt. Credentials are
    # bound to the RP ID above, so changing the name strands no one.
    webauthn_rp_name: str = Field(default=APP_NAME, validation_alias="WEBAUTHN_RP_NAME")
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

    # Report links: the key their tokens are stored under, as
    # HMAC-SHA256(key, token). It lives outside the database, so rotating it
    # ends every report link at once and a database restore cannot roll it
    # back. Its own key, not JWT_SECRET: rotating one must not do the other's
    # job. No default: a deployment without it refuses to boot.
    report_link_key: str = Field(validation_alias="REPORT_LINK_KEY")

    @field_validator("report_link_key")
    @classmethod
    def _validate_report_link_key_length(cls, v: str) -> str:
        """REPORT_LINK_KEY must be at least 32 bytes, as JWT_SECRET must.
        Generate one with: `openssl rand -base64 48`."""
        if len(v.encode("utf-8")) < REPORT_LINK_KEY_MIN_BYTES:
            raise ValueError(
                f"REPORT_LINK_KEY must be at least {REPORT_LINK_KEY_MIN_BYTES} bytes "
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

    # Single sign-on through OpenID Connect (optional second front door)
    #
    # Beats keeps its own email + passkey login exactly as it is. Each entry
    # here adds a "Continue with <name>" button for one OIDC provider —
    # Google, Microsoft, Keycloak, Authentik, anything that publishes
    # `/.well-known/openid-configuration`. Empty (the default) means no
    # buttons and /api/auth/sso/* answering that nothing is configured.
    #
    # Set as JSON, e.g.
    #   OIDC_PROVIDERS='[{"id": "google", "name": "Google",
    #     "issuer": "https://accounts.google.com",
    #     "client_id": "…", "client_secret": "…"}]'
    oidc_providers: list[OIDCProviderSettings] = Field(
        default_factory=list, validation_alias="OIDC_PROVIDERS"
    )

    # Where every provider sends the browser back: the web app's
    # `/auth/callback`, which hands the code to the API. Register exactly
    # this URL with each provider. One per deployment — `https://lifepete.com/auth/callback`
    # for the split deployment, the same origin as the API for a single-origin
    # one. Required as soon as one provider is configured: guessing it from
    # a request's Host would let that header choose where a code is sent.
    oidc_redirect_uri: str = Field(default="", validation_alias="OIDC_REDIRECT_URI")

    @model_validator(mode="after")
    def _validate_oidc(self) -> Settings:
        if not self.oidc_providers:
            return self
        if not self.oidc_redirect_uri:
            raise ValueError("OIDC_REDIRECT_URI is required when OIDC_PROVIDERS is set")
        _require_https(self.oidc_redirect_uri, "OIDC_REDIRECT_URI")
        ids = [p.id for p in self.oidc_providers]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"OIDC_PROVIDERS repeats the id(s): {', '.join(duplicates)}")
        return self

    # AI Coach (Stage 2)
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    # Sonnet 5.5, at $2/$10 per Mtok. Set COACH_MODEL=claude-opus-5-5 for the
    # stronger model at $4/$20 — gateway.MODEL_PRICING bills either correctly.
    coach_model: str = Field(default="claude-sonnet-5-5", validation_alias="COACH_MODEL")
    coach_monthly_budget_usd: float = Field(
        default=10.0, validation_alias="COACH_MONTHLY_BUDGET_USD"
    )


settings = Settings()
