"""GitHub service — OAuth flow and commit activity correlation."""

import logging
from datetime import date, timedelta
from urllib.parse import urlencode

import httpx

from beats.domain.models import GitHubIntegration
from beats.infrastructure.repositories import GitHubIntegrationRepository
from beats.settings import Settings

logger = logging.getLogger(__name__)

GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API = "https://api.github.com"
SCOPES = "repo:status read:user"


class GitHubService:
    """Service for GitHub OAuth flow and commit activity fetching."""

    def __init__(self, settings: Settings, repo: GitHubIntegrationRepository):
        self.settings = settings
        self.repo = repo

    def get_auth_url(self) -> str:
        """Generate the GitHub OAuth consent URL."""
        params = {
            "client_id": self.settings.github_client_id,
            "redirect_uri": self.settings.github_redirect_uri,
            "scope": SCOPES,
        }
        return f"{GITHUB_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> GitHubIntegration:
        """Exchange authorization code for an access token and store it."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                GITHUB_TOKEN_URL,
                data={
                    "client_id": self.settings.github_client_id,
                    "client_secret": self.settings.github_client_secret,
                    "code": code,
                    "redirect_uri": self.settings.github_redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        access_token = data.get("access_token", "")

        # Fetch GitHub username
        username = ""
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                user_resp = await client.get(
                    f"{GITHUB_API}/user",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github+json",
                    },
                )
                user_resp.raise_for_status()
                username = user_resp.json().get("login", "")
            except Exception:
                logger.warning("Failed to fetch GitHub user info")

        integration = GitHubIntegration(
            access_token=access_token,
            github_username=username,
        )
        return await self.repo.upsert(integration)

    async def fetch_commit_counts(
        self, repo_name: str, start: date, end: date
    ) -> list[dict]:
        """Fetch daily commit counts for a repo in a date range.

        Uses the per-user access token from the stored integration.
        """
        integration = await self.repo.get()
        if not integration or not integration.access_token:
            return []

        headers = {
            "Authorization": f"Bearer {integration.access_token}",
            "Accept": "application/vnd.github+json",
        }

        since = f"{start.isoformat()}T00:00:00Z"
        until = f"{(end + timedelta(days=1)).isoformat()}T00:00:00Z"

        commits_by_day: dict[str, int] = {}
        page = 1

        async with httpx.AsyncClient(timeout=15) as client:
            while True:
                try:
                    resp = await client.get(
                        f"{GITHUB_API}/repos/{repo_name}/commits",
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
                    logger.warning("Failed to fetch commits from %s", repo_name)
                    break

        return [
            {"date": day, "commit_count": count}
            for day, count in sorted(commits_by_day.items())
        ]

    async def disconnect(self) -> bool:
        """Remove the stored integration."""
        return await self.repo.delete()
