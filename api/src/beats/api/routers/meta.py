"""Meta API router — reference data the UI's contract settings need, static per release."""

from fastapi import APIRouter, Query, Response

from beats.domain.holidays import Region, RegionHoliday, region_holidays, regions

router = APIRouter(prefix="/api/meta", tags=["Meta"])


@router.get("/holiday-regions", response_model=list[Region])
async def list_holiday_regions(response: Response):
    """Every country the holiday calendar knows, with the subdivisions that
    change its calendar, for the contract's region picker.

    Public data, but behind the ordinary session auth like everything else:
    nothing here is worth a second public prefix. It changes only with a
    `holidays` release, hence cacheable for a day — `public` so a shared
    cache may keep it despite the Authorization header.
    """
    response.headers["Cache-Control"] = "public, max-age=86400"
    return regions()


@router.get("/holidays", response_model=list[RegionHoliday])
async def list_region_holidays(
    response: Response,
    country: str = Query(description="ISO 3166-1 alpha-2, as the region list gives it."),
    year: int = Query(ge=1, le=9999),
    subdivision: str | None = Query(default=None),
):
    """One region's public holidays for a year, by date and name, as the
    region gives them — no contract's company days or days not given. For
    the settings form, which must see the calendar of a region it has not
    saved yet. 400 `UNKNOWN_HOLIDAY_REGION` for a country or subdivision the
    calendar does not know. Cacheable for a day, like the region list: it
    changes only with a `holidays` release.
    """
    holidays = region_holidays(country, subdivision, year)
    response.headers["Cache-Control"] = "public, max-age=86400"
    return holidays
