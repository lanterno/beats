"""Oura service — personal access token integration and daily health data."""

import logging
from datetime import date as date_type

import httpx

from beats.domain.exceptions import DomainException
from beats.domain.models import OuraIntegration
from beats.infrastructure.repositories import OuraIntegrationRepository

logger = logging.getLogger(__name__)

OURA_API = "https://api.ouraring.com/v2"


class OuraService:
    """Service for Oura Ring data fetching via personal access token."""

    def __init__(self, repo: OuraIntegrationRepository):
        self.repo = repo

    async def connect(self, personal_access_token: str) -> OuraIntegration:
        """Validate a PAT by calling Oura's API, then store it."""
        headers = {"Authorization": f"Bearer {personal_access_token}"}

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{OURA_API}/usercollection/personal_info", headers=headers
            )
            if resp.status_code != 200:
                raise DomainException("Invalid Oura personal access token")
            user_info = resp.json()

        integration = OuraIntegration(
            access_token=personal_access_token,
            oura_user_id=user_info.get("id", ""),
        )
        return await self.repo.upsert(integration)

    async def fetch_daily(self, target_date: date_type) -> dict:
        """Fetch daily sleep and readiness data for a given date."""
        integration = await self.repo.get()
        if not integration:
            return {}

        headers = {"Authorization": f"Bearer {integration.access_token}"}
        date_str = target_date.isoformat()
        result: dict = {"source": "oura", "date": target_date}

        async with httpx.AsyncClient(timeout=15) as client:
            # Sleep
            try:
                resp = await client.get(
                    f"{OURA_API}/usercollection/daily_sleep",
                    params={"start_date": date_str, "end_date": date_str},
                    headers=headers,
                )
                if resp.status_code == 200:
                    sleep_items = resp.json().get("data", [])
                    if sleep_items:
                        day = sleep_items[0]
                        # Oura reports total_sleep_duration in seconds
                        total_sleep_sec = day.get("contributors", {}).get(
                            "total_sleep", 0
                        )
                        if total_sleep_sec:
                            result["sleep_minutes"] = total_sleep_sec // 60
                        result["sleep_efficiency"] = (
                            day.get("score", 0) / 100.0 if day.get("score") else None
                        )
            except httpx.HTTPError:
                logger.debug("Oura sleep fetch failed", exc_info=True)

            # Readiness
            try:
                resp = await client.get(
                    f"{OURA_API}/usercollection/daily_readiness",
                    params={"start_date": date_str, "end_date": date_str},
                    headers=headers,
                )
                if resp.status_code == 200:
                    readiness_items = resp.json().get("data", [])
                    if readiness_items:
                        result["readiness_score"] = readiness_items[0].get("score")
            except httpx.HTTPError:
                logger.debug("Oura readiness fetch failed", exc_info=True)

            # HRV (from sleep periods)
            try:
                resp = await client.get(
                    f"{OURA_API}/usercollection/sleep",
                    params={"start_date": date_str, "end_date": date_str},
                    headers=headers,
                )
                if resp.status_code == 200:
                    sleep_periods = resp.json().get("data", [])
                    if sleep_periods:
                        hrv = sleep_periods[0].get("average_hrv")
                        if hrv:
                            result["hrv_ms"] = float(hrv)
                        result["resting_hr_bpm"] = sleep_periods[0].get(
                            "lowest_heart_rate"
                        )
            except httpx.HTTPError:
                logger.debug("Oura HRV fetch failed", exc_info=True)

        return result

    async def disconnect(self) -> bool:
        """Remove the Oura integration."""
        return await self.repo.delete()
