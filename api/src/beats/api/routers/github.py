"""GitHub API router — OAuth flow and integration status."""

from fastapi import APIRouter

from beats.api.dependencies import GitHubServiceDep

router = APIRouter(prefix="/api/github", tags=["github"])


@router.get("/auth-url")
async def get_auth_url(service: GitHubServiceDep):
    """Get the GitHub OAuth consent URL to start the connection flow."""
    return {"url": service.get_auth_url()}


@router.post("/connect")
async def connect_github(code: str, service: GitHubServiceDep):
    """Exchange an OAuth authorization code for a token and store the integration."""
    integration = await service.exchange_code(code)
    return {
        "connected": True,
        "github_username": integration.github_username,
    }


@router.delete("/disconnect")
async def disconnect_github(service: GitHubServiceDep):
    """Remove the GitHub integration."""
    deleted = await service.disconnect()
    return {"disconnected": deleted}


@router.get("/status")
async def github_status(service: GitHubServiceDep):
    """Check if a GitHub integration is connected."""
    integration = await service.repo.get()
    return {
        "connected": integration is not None and integration.enabled,
        "github_username": integration.github_username if integration else None,
    }
