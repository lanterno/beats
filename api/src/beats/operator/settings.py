"""The operator deployment's settings — and nothing of the API's.

Deliberately not `beats.settings`, which requires `JWT_SECRET`: the operator
deployment never holds it, because holding it is holding every user's session
(roadmaps/backoffice.md § Authentication). That isn't a rule enforced at
runtime — this class simply has no such field, and `operator_server` composes
nothing that reads it.
"""

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_api_dir = Path(__file__).resolve().parent.parent.parent.parent

# Named like BEATS_ENV_FILE and for the same reason (beats/settings.py): which
# file to load is said, never inferred. `.env.operator` is gitignored like
# `.env`.
_env_file = _api_dir / os.getenv("BEATS_OPERATOR_ENV_FILE", ".env.operator")


class OperatorIdentity(BaseModel):
    """One person the allowlist admits, keyed on IAP's stable `sub`.

    The email is shown on `/me` and in the audit, never matched: an address
    can change hands, which is the same reason an SSO identity is keyed on
    issuer + subject (`auth/sso_accounts.py`). Two roles from day one, so a
    second person can look without acting: a `viewer` reads every page and
    runs no command.
    """

    sub: str = Field(min_length=1)
    email: str = ""
    role: Literal["viewer", "operator"] = "viewer"


class OperatorSettings(BaseSettings):
    # Same reasoning as Settings (beats/settings.py): a failed start must not
    # print the env mapping it read.
    model_config = SettingsConfigDict(
        env_file=_env_file,
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    # The operator's own database credential — in production a user whose
    # grant is the short write list in roadmaps/backoffice.md
    # § Infrastructure, never the API's.
    db_dsn: str = Field(default="mongodb://localhost:27017", validation_alias="OPERATOR_DB_DSN")
    db_name: str = Field(default="beats", validation_alias="OPERATOR_DB_NAME")

    # The IAP audience the assertion's `aud` must equal:
    # /projects/PROJECT_NUMBER/locations/REGION/services/beats-operator,
    # with the project number, not its id.
    iap_audience: str = Field(default="", validation_alias="OPERATOR_IAP_AUDIENCE")

    # Locally, stands in for the IAP assertion the way BEATS_TEST_ENV stands
    # in for testcontainers: the value is the `sub` every request is treated
    # as. Exactly one of it and the audience may be set — a stand-in left in
    # a deployment's environment stops the deploy instead of replacing the
    # wall, and a deployment with neither has no way in rather than an open
    # one.
    dev_operator: str = Field(default="", validation_alias="BACKOFFICE_DEV_OPERATOR")

    # Who may act, by IAP's `sub`. IAP's IAM binding says who reaches the
    # app; this says what they may do, so an IAM grant made by mistake
    # reaches a 403. JSON, e.g.
    #   OPERATOR_ALLOWLIST='[{"sub": "accounts.google.com:1234",
    #     "email": "op@example.com", "role": "operator"}]'
    allowlist: list[OperatorIdentity] = Field(
        default_factory=list, validation_alias="OPERATOR_ALLOWLIST"
    )

    # The app's own origin, which the command check compares `Origin`
    # against: the run.app URL in production, the Vite dev server locally.
    origin: str = Field(default="http://localhost:8081", validation_alias="OPERATOR_ORIGIN")

    # Mirrors the API's COACH_MONTHLY_BUDGET_USD — the operator deployment
    # cannot read beats.settings, so what "near the cap" means on the landing
    # page is set here, to the same value. Display and attention math only;
    # the API's own setting is what refuses.
    coach_monthly_budget_usd: float = Field(
        default=10.0, validation_alias="COACH_MONTHLY_BUDGET_USD"
    )

    @model_validator(mode="after")
    def _exactly_one_door(self) -> OperatorSettings:
        if bool(self.iap_audience) == bool(self.dev_operator):
            raise ValueError(
                "exactly one of OPERATOR_IAP_AUDIENCE and BACKOFFICE_DEV_OPERATOR must be set: "
                "the audience is production's wall, the stand-in is local development's, and "
                "neither means no way in"
            )
        subs = [i.sub for i in self.allowlist]
        duplicates = sorted({s for s in subs if subs.count(s) > 1})
        if duplicates:
            raise ValueError(f"OPERATOR_ALLOWLIST repeats the sub(s): {', '.join(duplicates)}")
        return self

    def identity_for(self, sub: str) -> OperatorIdentity | None:
        return next((i for i in self.allowlist if i.sub == sub), None)
