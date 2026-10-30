import ipaddress
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
    model_config = SettingsConfigDict(
        env_file=_env_file,
        env_file_encoding="utf-8",
        extra="ignore",
        # A validation error here is printed by whatever failed to start —
        # locally in a terminal, on Cloud Run into the revision's logs. With
        # inputs shown, a missing field lists every other setting's value
        # (`input_value={'DB_DSN': 'mongodb://…'}`), and a too-short
        # JWT_SECRET is echoed whole.
        hide_input_in_errors=True,
    )

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

    # The proxies in front of this API whose X-Forwarded-For is believed, as
    # IP addresses and CIDR networks, comma-separated. The client's address —
    # what every rate limit keys on — is the right-most X-Forwarded-For entry
    # not written by one of them (uvicorn's ProxyHeadersMiddleware, which
    # server.py installs with this list). Each proxy appends the address it
    # saw, so that entry is the one a client cannot write itself; the entries
    # to its left are whatever the client sent.
    #
    # Required, and no `*`: every deployment names its own proxies, because a
    # wrong value fails quietly in one of two ways. Trust too little and every
    # visitor shares the proxy's address and one rate-limit bucket (what Cloud
    # Run's front end did to all of them, at 169.254.169.126); trust everything
    # and a client picks its own address, and with it a fresh bucket per
    # request.
    #   Cloud Run  169.254.0.0/16 (terraform/cloudrun.tf: the platform connects
    #              from link-local, which nothing on the internet can)
    #   self-host  the compose network nginx proxies from (compose.selfhost.yml)
    #   local      127.0.0.1: nothing stands in front, and loopback is this machine
    forwarded_allow_ips: str = Field(validation_alias="FORWARDED_ALLOW_IPS")

    @field_validator("forwarded_allow_ips")
    @classmethod
    def _validate_forwarded_allow_ips(cls, v: str) -> str:
        """Every entry an address or a network, checked here because uvicorn
        reads one it cannot parse as a name no address ever matches, which
        would trust nothing without saying so."""
        entries = [entry.strip() for entry in v.split(",")]
        for entry in entries:
            if entry == "*":
                raise ValueError(
                    "FORWARDED_ALLOW_IPS must name the proxies, not '*': trusting every "
                    "address lets a client choose its own address in X-Forwarded-For"
                )
            try:
                network = ipaddress.ip_network(entry)
            except ValueError:
                raise ValueError(
                    f"FORWARDED_ALLOW_IPS entry {entry!r} is not an IP address or a "
                    "CIDR network (one with no host bits set, e.g. 169.254.0.0/16)"
                ) from None
            if network.prefixlen == 0:
                raise ValueError(
                    f"FORWARDED_ALLOW_IPS entry {entry!r} spans every address, which is '*'"
                )
        return ",".join(entries)

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
