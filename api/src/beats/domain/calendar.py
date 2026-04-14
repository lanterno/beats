"""Calendar service — Google Calendar OAuth and event fetching."""

import logging
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx

from beats.domain.models import CalendarIntegration
from beats.infrastructure.repositories import CalendarIntegrationRepository
from beats.settings import Settings

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"
SCOPES = "https://www.googleapis.com/auth/calendar.events.readonly"


class CalendarService:
    """Service for Google Calendar OAuth flow and event fetching."""

    def __init__(self, settings: Settings, repo: CalendarIntegrationRepository):
        self.settings = settings
        self.repo = repo

    def get_auth_url(self) -> str:
        """Generate the Google OAuth consent URL."""
        params = {
            "client_id": self.settings.google_client_id,
            "redirect_uri": self.settings.google_redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> CalendarIntegration:
        """Exchange authorization code for tokens and store them."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(GOOGLE_TOKEN_URL, data={
                "code": code,
                "client_id": self.settings.google_client_id,
                "client_secret": self.settings.google_client_secret,
                "redirect_uri": self.settings.google_redirect_uri,
                "grant_type": "authorization_code",
            })
            resp.raise_for_status()
            data = resp.json()

        integration = CalendarIntegration(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", ""),
            token_expiry=datetime.fromtimestamp(
                datetime.now(UTC).timestamp() + data.get("expires_in", 3600), tz=UTC
            ),
        )
        return await self.repo.upsert(integration)

    async def _ensure_fresh_token(self, integration: CalendarIntegration) -> CalendarIntegration:
        """Refresh the access token if expired."""
        if integration.token_expiry and integration.token_expiry > datetime.now(UTC):
            return integration

        if not integration.refresh_token:
            return integration

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(GOOGLE_TOKEN_URL, data={
                "client_id": self.settings.google_client_id,
                "client_secret": self.settings.google_client_secret,
                "refresh_token": integration.refresh_token,
                "grant_type": "refresh_token",
            })
            resp.raise_for_status()
            data = resp.json()

        integration.access_token = data["access_token"]
        integration.token_expiry = datetime.fromtimestamp(
            datetime.now(UTC).timestamp() + data.get("expires_in", 3600), tz=UTC
        )
        return await self.repo.upsert(integration)

    async def fetch_events(
        self, start: datetime, end: datetime
    ) -> list[dict]:
        """Fetch calendar events in a time range."""
        integration = await self.repo.get()
        if not integration or not integration.enabled:
            return []

        integration = await self._ensure_fresh_token(integration)

        events = []
        for cal_id in integration.calendar_ids:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(
                        f"{GOOGLE_CALENDAR_API}/calendars/{cal_id}/events",
                        headers={"Authorization": f"Bearer {integration.access_token}"},
                        params={
                            "timeMin": start.isoformat(),
                            "timeMax": end.isoformat(),
                            "singleEvents": "true",
                            "orderBy": "startTime",
                            "maxResults": "100",
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()

                for item in data.get("items", []):
                    event_start = item.get("start", {})
                    event_end = item.get("end", {})
                    events.append({
                        "summary": item.get("summary", "(No title)"),
                        "start": event_start.get("dateTime") or event_start.get("date", ""),
                        "end": event_end.get("dateTime") or event_end.get("date", ""),
                        "all_day": "date" in event_start and "dateTime" not in event_start,
                    })
            except Exception:
                logger.warning("Failed to fetch events from calendar %s", cal_id)

        return events

    async def disconnect(self) -> bool:
        """Remove the stored integration."""
        return await self.repo.delete()
