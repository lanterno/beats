"""Fitbit service — OAuth flow and daily health data fetching."""

import logging
from datetime import UTC, datetime
from datetime import date as date_type
from urllib.parse import urlencode

import httpx

from beats.domain.models import FitbitIntegration
from beats.infrastructure.repositories import FitbitIntegrationRepository
from beats.settings import Settings

logger = logging.getLogger(__name__)

FITBIT_AUTH_URL = "https://www.fitbit.com/oauth2/authorize"
FITBIT_TOKEN_URL = "https://api.fitbit.com/oauth2/token"
FITBIT_API = "https://api.fitbit.com"
SCOPES = "activity heartrate sleep"


class FitbitService:
    """Service for Fitbit OAuth flow and daily health data fetching."""

    def __init__(self, settings: Settings, repo: FitbitIntegrationRepository):
        self.settings = settings
        self.repo = repo

    def get_auth_url(self) -> str:
        """Generate the Fitbit OAuth consent URL."""
        params = {
            "client_id": self.settings.fitbit_client_id,
            "redirect_uri": self.settings.fitbit_redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
        }
        return f"{FITBIT_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> FitbitIntegration:
        """Exchange authorization code for tokens and store them."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                FITBIT_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self.settings.fitbit_client_id,
                    "client_secret": self.settings.fitbit_client_secret,
                    "redirect_uri": self.settings.fitbit_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        integration = FitbitIntegration(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", ""),
            token_expiry=datetime.fromtimestamp(
                datetime.now(UTC).timestamp() + data.get("expires_in", 28800), tz=UTC
            ),
            fitbit_user_id=data.get("user_id", ""),
        )
        return await self.repo.upsert(integration)

    async def _ensure_fresh_token(self, integration: FitbitIntegration) -> FitbitIntegration:
        """Refresh the access token if expired."""
        if integration.token_expiry and integration.token_expiry > datetime.now(UTC):
            return integration

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                FITBIT_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": integration.refresh_token,
                    "client_id": self.settings.fitbit_client_id,
                    "client_secret": self.settings.fitbit_client_secret,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        integration.access_token = data["access_token"]
        integration.refresh_token = data.get("refresh_token", integration.refresh_token)
        integration.token_expiry = datetime.fromtimestamp(
            datetime.now(UTC).timestamp() + data.get("expires_in", 28800), tz=UTC
        )
        return await self.repo.upsert(integration)

    async def fetch_daily(self, target_date: date_type) -> dict:
        """Fetch daily sleep, heart rate, and activity data for a given date."""
        integration = await self.repo.get()
        if not integration:
            return {}

        integration = await self._ensure_fresh_token(integration)
        date_str = target_date.isoformat()
        headers = {"Authorization": f"Bearer {integration.access_token}"}

        result: dict = {"source": "fitbit", "date": target_date}

        async with httpx.AsyncClient(timeout=15) as client:
            # Sleep
            try:
                resp = await client.get(
                    f"{FITBIT_API}/1.2/user/-/sleep/date/{date_str}.json",
                    headers=headers,
                )
                if resp.status_code == 200:
                    sleep_data = resp.json()
                    if sleep_data.get("summary"):
                        result["sleep_minutes"] = sleep_data["summary"].get("totalMinutesAsleep")
                        total_time = sleep_data["summary"].get("totalTimeInBed", 0)
                        if total_time > 0:
                            result["sleep_efficiency"] = (
                                sleep_data["summary"].get("totalMinutesAsleep", 0) / total_time
                            )
            except httpx.HTTPError:
                logger.debug("Fitbit sleep fetch failed", exc_info=True)

            # Heart rate
            try:
                resp = await client.get(
                    f"{FITBIT_API}/1/user/-/activities/heart/date/{date_str}/1d.json",
                    headers=headers,
                )
                if resp.status_code == 200:
                    hr_data = resp.json()
                    hr_value = hr_data.get("activities-heart", [{}])[0].get("value", {})
                    result["resting_hr_bpm"] = hr_value.get("restingHeartRate")
            except httpx.HTTPError:
                logger.debug("Fitbit heart rate fetch failed", exc_info=True)

            # Steps
            try:
                resp = await client.get(
                    f"{FITBIT_API}/1/user/-/activities/date/{date_str}.json",
                    headers=headers,
                )
                if resp.status_code == 200:
                    act_data = resp.json()
                    result["steps"] = act_data.get("summary", {}).get("steps")
            except httpx.HTTPError:
                logger.debug("Fitbit activity fetch failed", exc_info=True)

        return result

    async def disconnect(self) -> bool:
        """Remove the Fitbit integration."""
        return await self.repo.delete()
