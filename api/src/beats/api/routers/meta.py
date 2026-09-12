"""Meta API router — reference data the UI's pickers need, static per release."""

from fastapi import APIRouter, Response

from beats.domain.holidays import Region, regions

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
