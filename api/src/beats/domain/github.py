"""GitHub service — commit activity correlation."""

import logging
from datetime import date, timedelta

import httpx

from beats.settings import Settings

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


class GitHubService:
    """Service for fetching GitHub commit activity."""

    def __init__(self, settings: Settings):
        self.token = settings.github_token

    async def fetch_commit_counts(
        self, repo: str, start: date, end: date
    ) -> list[dict]:
        """Fetch daily commit counts for a repo in a date range.

        Args:
            repo: GitHub repo in "owner/repo" format.
            start: Start date (inclusive).
            end: End date (inclusive).

        Returns:
            List of dicts with date and commit_count.
        """
        if not self.token:
            return []

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
        }

        # Fetch commits in date range
        since = f"{start.isoformat()}T00:00:00Z"
        until = f"{(end + timedelta(days=1)).isoformat()}T00:00:00Z"

        commits_by_day: dict[str, int] = {}
        page = 1

        async with httpx.AsyncClient(timeout=15) as client:
            while True:
                try:
                    resp = await client.get(
                        f"{GITHUB_API}/repos/{repo}/commits",
                        headers=headers,
                        params={
                            "since": since,
                            "until": until,
                            "per_page": 100,
                            "page": page,
                        },
                    )
                    resp.raise_for_status()
                    items = resp.json()

                    if not items:
                        break

                    for commit in items:
                        commit_date = commit.get("commit", {}).get("author", {}).get("date", "")
                        if commit_date:
                            day_str = commit_date[:10]
                            commits_by_day[day_str] = commits_by_day.get(day_str, 0) + 1

                    if len(items) < 100:
                        break
                    page += 1
                except Exception:
                    logger.warning("Failed to fetch commits from %s", repo)
                    break

        return [
            {"date": day, "commit_count": count}
            for day, count in sorted(commits_by_day.items())
        ]
