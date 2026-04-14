"""Auto-start rules API router — CRUD and webhook trigger for auto-starting timers."""

import http
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from beats.api.dependencies import AutoStartRuleRepoDep, TimerServiceDep
from beats.domain.models import AutoStartRule

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auto-start", tags=["auto-start"])


class CreateAutoStartRuleRequest(BaseModel):
    type: str  # "webhook_trigger" or "schedule"
    project_id: str
    config: dict = {}  # e.g. {"repo": "owner/repo"} or {"cron": "0 9 * * 1-5"}


@router.get("/")
async def list_rules(repo: AutoStartRuleRepoDep):
    """List all auto-start rules."""
    rules = await repo.list_all()
    return [r.model_dump(mode="json") for r in rules]


@router.post("/", status_code=http.HTTPStatus.CREATED)
async def create_rule(request: CreateAutoStartRuleRequest, repo: AutoStartRuleRepoDep):
    """Create a new auto-start rule."""
    rule = AutoStartRule(
        type=request.type,
        project_id=request.project_id,
        config=request.config,
    )
    created = await repo.create(rule)
    return created.model_dump(mode="json")


@router.delete("/{rule_id}")
async def delete_rule(rule_id: str, repo: AutoStartRuleRepoDep):
    """Delete an auto-start rule."""
    deleted = await repo.delete(rule_id)
    return {"deleted": deleted}


class WebhookTriggerPayload(BaseModel):
    """Payload from an external webhook (e.g. GitHub push)."""

    repository: str = ""  # "owner/repo"


@router.post("/trigger")
async def trigger_auto_start(
    payload: WebhookTriggerPayload,
    repo: AutoStartRuleRepoDep,
    timer_service: TimerServiceDep,
):
    """Receive an external webhook and start the timer if a matching rule exists.

    Call this from GitHub webhook, Zapier, etc. with {"repository": "owner/repo"}.
    """
    rules = await repo.list_by_type("webhook_trigger")
    for rule in rules:
        rule_repo = rule.config.get("repo", "")
        if rule_repo and rule_repo == payload.repository:
            try:
                beat = await timer_service.start_timer(rule.project_id)
                return {
                    "started": True,
                    "project_id": rule.project_id,
                    "beat_id": beat.id,
                }
            except Exception as e:
                return {"started": False, "reason": str(e)}

    return {"started": False, "reason": "No matching rule found"}
