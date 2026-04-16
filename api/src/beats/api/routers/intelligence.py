"""Intelligence API router — productivity scoring, patterns, digests, and suggestions."""

from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query, Response

from beats.api.dependencies import (
    InsightsRepoDep,
    IntelligenceServiceDep,
    WeeklyDigestRepoDep,
)
from beats.api.schemas import (
    EstimationAccuracyResponse,
    FocusScoreResponse,
    InboxItemResponse,
    InboxResponse,
    InsightCardResponse,
    MoodCorrelationResponse,
    PatternsResponse,
    ProductivityScoreResponse,
    ProjectHealthResponse,
    ScoreHistoryItem,
    SuggestionResponse,
    WeeklyDigestResponse,
)

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


@router.get("/score", response_model=ProductivityScoreResponse)
async def get_productivity_score(
    service: IntelligenceServiceDep,
) -> ProductivityScoreResponse:
    """Get current productivity score (0-100) with component breakdown."""
    result = await service.compute_productivity_score()
    return ProductivityScoreResponse(**result)


@router.get("/score/history", response_model=list[ScoreHistoryItem])
async def get_score_history(
    service: IntelligenceServiceDep,
    weeks: int = Query(default=8, ge=1, le=52),
) -> list[ScoreHistoryItem]:
    """Get weekly productivity score history for sparkline."""
    history = await service.compute_productivity_score_history(weeks=weeks)
    return [ScoreHistoryItem(**item) for item in history]


@router.get("/digests", response_model=list[WeeklyDigestResponse])
async def list_digests(
    digest_repo: WeeklyDigestRepoDep,
    limit: int = Query(default=12, ge=1, le=52),
) -> list[WeeklyDigestResponse]:
    """List recent weekly digests."""
    digests = await digest_repo.list_recent(limit=limit)
    return [
        WeeklyDigestResponse(
            id=d.id,
            week_of=d.week_of,
            generated_at=d.generated_at,
            total_hours=d.total_hours,
            session_count=d.session_count,
            active_days=d.active_days,
            top_project_id=d.top_project_id,
            top_project_name=d.top_project_name,
            top_project_hours=d.top_project_hours,
            vs_last_week_pct=d.vs_last_week_pct,
            longest_day=d.longest_day,
            longest_day_hours=d.longest_day_hours,
            best_streak=d.best_streak,
            observation=d.observation,
            project_breakdown=d.project_breakdown,
            productivity_score=d.productivity_score,
        )
        for d in digests
    ]


@router.get("/digests/{week_of}", response_model=WeeklyDigestResponse)
async def get_digest(
    digest_repo: WeeklyDigestRepoDep,
    week_of: date,
) -> WeeklyDigestResponse:
    """Get a specific weekly digest by its Monday date."""
    from fastapi import HTTPException

    digest = await digest_repo.get_by_week(week_of)
    if not digest:
        raise HTTPException(status_code=404, detail="Digest not found for this week")
    return WeeklyDigestResponse(
        id=digest.id,
        week_of=digest.week_of,
        generated_at=digest.generated_at,
        total_hours=digest.total_hours,
        session_count=digest.session_count,
        active_days=digest.active_days,
        top_project_id=digest.top_project_id,
        top_project_name=digest.top_project_name,
        top_project_hours=digest.top_project_hours,
        vs_last_week_pct=digest.vs_last_week_pct,
        longest_day=digest.longest_day,
        longest_day_hours=digest.longest_day_hours,
        best_streak=digest.best_streak,
        observation=digest.observation,
        project_breakdown=digest.project_breakdown,
        productivity_score=digest.productivity_score,
    )


@router.post("/digests/generate", response_model=WeeklyDigestResponse)
async def generate_digest(
    service: IntelligenceServiceDep,
    digest_repo: WeeklyDigestRepoDep,
    week_of: Annotated[date | None, Query()] = None,
) -> WeeklyDigestResponse:
    """Generate (or regenerate) a weekly digest. Defaults to last completed week."""
    if week_of is None:
        today = datetime.now(UTC).date()
        # Last completed week's Monday
        week_of = today - timedelta(days=today.weekday() + 7)

    digest = await service.generate_weekly_digest(week_of)
    await digest_repo.upsert(digest)
    return WeeklyDigestResponse(
        id=digest.id,
        week_of=digest.week_of,
        generated_at=digest.generated_at,
        total_hours=digest.total_hours,
        session_count=digest.session_count,
        active_days=digest.active_days,
        top_project_id=digest.top_project_id,
        top_project_name=digest.top_project_name,
        top_project_hours=digest.top_project_hours,
        vs_last_week_pct=digest.vs_last_week_pct,
        longest_day=digest.longest_day,
        longest_day_hours=digest.longest_day_hours,
        best_streak=digest.best_streak,
        observation=digest.observation,
        project_breakdown=digest.project_breakdown,
        productivity_score=digest.productivity_score,
    )


@router.get("/patterns", response_model=PatternsResponse)
async def get_patterns(
    insights_repo: InsightsRepoDep,
) -> PatternsResponse:
    """Get cached pattern detection results."""
    user_insights = await insights_repo.get()
    if not user_insights:
        return PatternsResponse(insights=[], generated_at=datetime.now(UTC))
    return PatternsResponse(
        insights=[
            InsightCardResponse(**i.model_dump())
            for i in user_insights.insights
            if i.id not in user_insights.dismissed_ids
        ],
        generated_at=user_insights.generated_at,
    )


@router.post("/patterns/refresh", response_model=PatternsResponse)
async def refresh_patterns(
    service: IntelligenceServiceDep,
    insights_repo: InsightsRepoDep,
) -> PatternsResponse:
    """Refresh pattern detection — recomputes all insights."""
    from beats.domain.models import UserInsights

    insights = await service.detect_patterns()
    user_insights = await insights_repo.get()
    dismissed = user_insights.dismissed_ids if user_insights else []

    new_insights = UserInsights(insights=insights, dismissed_ids=dismissed)
    await insights_repo.upsert(new_insights)

    return PatternsResponse(
        insights=[InsightCardResponse(**i.model_dump()) for i in insights if i.id not in dismissed],
        generated_at=new_insights.generated_at,
    )


@router.post("/patterns/{insight_id}/dismiss", status_code=204)
async def dismiss_pattern(
    insights_repo: InsightsRepoDep,
    insight_id: str,
) -> Response:
    """Dismiss a pattern insight card."""
    await insights_repo.dismiss_insight(insight_id)
    return Response(status_code=204)


@router.get("/suggestions", response_model=list[SuggestionResponse])
async def get_suggestions(
    service: IntelligenceServiceDep,
    target_date: Annotated[date | None, Query(alias="date")] = None,
) -> list[SuggestionResponse]:
    """Get smart daily plan suggestions for a date (defaults to today)."""
    d = target_date or datetime.now(UTC).date()
    results = await service.suggest_daily_plan(d)
    return [SuggestionResponse(**r) for r in results]


@router.get("/focus-scores", response_model=list[FocusScoreResponse])
async def get_focus_scores(
    service: IntelligenceServiceDep,
    target_date: Annotated[date | None, Query(alias="date")] = None,
) -> list[FocusScoreResponse]:
    """Get focus quality scores for all sessions on a date (defaults to today)."""
    d = target_date or datetime.now(UTC).date()
    results = await service.compute_focus_scores(d)
    return [FocusScoreResponse(**r) for r in results]


@router.get("/mood", response_model=MoodCorrelationResponse)
async def get_mood_correlation(
    service: IntelligenceServiceDep,
) -> MoodCorrelationResponse:
    """Get mood-productivity correlation analysis."""
    result = await service.get_mood_correlation()
    return MoodCorrelationResponse(**result)


@router.get("/estimation", response_model=list[EstimationAccuracyResponse])
async def get_estimation_accuracy(
    service: IntelligenceServiceDep,
) -> list[EstimationAccuracyResponse]:
    """Get per-project estimation accuracy (planned vs actual)."""
    results = await service.get_estimation_accuracy()
    return [EstimationAccuracyResponse(**r) for r in results]


@router.get("/project-health", response_model=list[ProjectHealthResponse])
async def get_project_health(
    service: IntelligenceServiceDep,
) -> list[ProjectHealthResponse]:
    """Get health metrics for each active project."""
    results = await service.get_project_health()
    return [ProjectHealthResponse(**r) for r in results]


def _pattern_severity(priority: int) -> str:
    if priority <= 1:
        return "high"
    if priority == 2:
        return "medium"
    return "low"


@router.get("/inbox", response_model=InboxResponse)
async def get_inbox(
    service: IntelligenceServiceDep,
    insights_repo: InsightsRepoDep,
    limit_suggestions: int = Query(default=3, ge=0, le=10),
) -> InboxResponse:
    """Aggregated Inbox: patterns, top suggestions for today, and project-health alerts.

    A read-model over existing intelligence outputs — no new computation, just a
    normalized view so the dashboard can surface everything in one place. Pattern
    dismiss state is honored via the existing insights repo.
    """

    items: list[InboxItemResponse] = []

    # Patterns (honor dismissed)
    user_insights = await insights_repo.get()
    if user_insights:
        for insight in user_insights.insights:
            if insight.id in user_insights.dismissed_ids:
                continue
            items.append(
                InboxItemResponse(
                    id=f"pattern:{insight.id}",
                    kind="pattern",
                    severity=_pattern_severity(insight.priority),
                    title=insight.title,
                    body=insight.body,
                    data=insight.model_dump().get("data", {}),
                )
            )

    # Daily suggestions (top N by suggested_minutes)
    today = datetime.now(UTC).date()
    suggestions = await service.suggest_daily_plan(today)
    suggestions_sorted = sorted(
        suggestions, key=lambda s: s.get("suggested_minutes", 0), reverse=True
    )
    for suggestion in suggestions_sorted[:limit_suggestions]:
        project_id = suggestion.get("project_id", "")
        project_name = suggestion.get("project_name", "")
        minutes = suggestion.get("suggested_minutes", 0)
        items.append(
            InboxItemResponse(
                id=f"suggestion:{project_id}:{today.isoformat()}",
                kind="suggestion",
                severity="low",
                title=f"Plan {minutes} min on {project_name}",
                body=suggestion.get("reasoning", ""),
                cta_label="Open project",
                cta_href=f"/project/{project_id}",
                data={"project_id": project_id, "suggested_minutes": minutes},
            )
        )

    # Project health alerts
    health = await service.get_project_health()
    for entry in health:
        alert = entry.get("alert")
        if not alert:
            continue
        project_id = entry.get("project_id", "")
        items.append(
            InboxItemResponse(
                id=f"project_health:{project_id}",
                kind="project_health",
                severity="medium",
                title=f"{entry.get('project_name', 'Project')} needs attention",
                body=alert,
                cta_label="Open project",
                cta_href=f"/project/{project_id}",
                data={
                    "project_id": project_id,
                    "days_since_last": entry.get("days_since_last"),
                },
            )
        )

    # Order: high → medium → low, preserving within-group order
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda it: severity_rank.get(it.severity, 3))

    return InboxResponse(items=items, generated_at=datetime.now(UTC))
