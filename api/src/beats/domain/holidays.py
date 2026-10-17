"""A contract's holidays — the only importer of the `holidays` package.

Everything downstream takes holidays as a plain `set[date]`, so the arithmetic
in `contracts.py` never touches this module and the library is exchangeable
from one place. What is exposed: the dates in a range for one region, a
region's year as the settings form previews it (`region_holidays`), the
holidays of one contract (`contract_calendar`, `contract_holidays` — the one
place the region's calendar meets the employer's own additions and removals),
the list of regions for a picker, and the check the project service runs on a
(country, subdivision) pair before a contract is written. Each holiday comes
with its name; a caller that only wants the dates takes the mapping's keys.

Names are in English, which is what the app speaks: a region whose own
language is English keeps its spelling (the UK's "Boxing Day"), any other
gives its US English names where the library has them ("Second Day of
Christmas" for "Zweiter Weihnachtstag"), and the rest keep the region's own.
The language is always passed: left out, the library follows the process
locale, so a container on `C` answered "Fronleichnam" where a laptop on
`en_US` answered "Corpus Christi".
"""

from datetime import date
from enum import StrEnum
from functools import cache

import holidays as holidays_lib
from holidays import registry
from pydantic import BaseModel

from beats.domain.exceptions import UnknownHolidayRegion
from beats.domain.models import Contract


class HolidaySource(StrEnum):
    """Where a contract's holiday comes from: the region's public calendar,
    or the employer's own list on the contract."""

    REGION = "region"
    COMPANY = "company"


class Holiday(BaseModel):
    """One holiday of a contract, as the calendar shows it. `given` is false
    only for a region holiday the employer does not give — a working day,
    listed so it can be shown by name."""

    date: date
    name: str
    source: HolidaySource
    given: bool


class RegionHoliday(BaseModel):
    """One public holiday of a region, as the region gives it: no contract's
    additions or removals."""

    date: date
    name: str


class Subdivision(BaseModel):
    code: str
    name: str


class Region(BaseModel):
    """One country in the picker, with the subdivisions that change its calendar."""

    code: str  # ISO 3166-1 alpha-2
    name: str
    subdivisions: list[Subdivision]


def named_holidays_between(
    country: str, subdivision: str | None, start: date, end: date
) -> dict[date, str]:
    """Every public holiday in the region falling within [start, end], by name.

    Two holidays on one day come back as one entry with both names, joined
    the way the library joins them ("Christmas Day; Boxing Day (observed)").
    """
    found: dict[date, str] = {}
    for year in range(start.year, end.year + 1):
        found.update(
            (day, name)
            for day, name in _year(country, subdivision, year).items()
            if start <= day <= end
        )
    return found


def region_holidays(country: str, subdivision: str | None, year: int) -> list[RegionHoliday]:
    """The region's public holidays in `year`, by date. A region a contract
    does not name yet has no contract to read them through: the settings form
    asks for this one before saving a region change, to say which dates the
    contract marks as not given the new region has a holiday on.
    Raises `UnknownHolidayRegion` unless `check_region` passes."""
    check_region(country, subdivision)
    region = named_holidays_between(country, subdivision, date(year, 1, 1), date(year, 12, 31))
    return [RegionHoliday(date=day, name=name) for day, name in sorted(region.items())]


def contract_calendar(
    contract: Contract, start: date, end: date, *, include_not_given: bool = False
) -> list[Holiday]:
    """The contract's holidays within [start, end], by date: the region's,
    less the ones the employer does not give, plus the company's.

    A region holiday on `holidays_not_given` is a working day; it is left
    out, or with `include_not_given` listed as `given=False`. A removal
    that matches no region holiday does nothing. A company day on a date
    the region already gives changes nothing and the region's name stands;
    on a removed date it wins, under its own name — the employer gives
    that day off after all. With `include_not_given` the region's row is
    still listed beside it, as not given, so that date comes twice: the
    editor must see both marks to clear one. Without a region only the
    company days count.
    Raises `UnknownHolidayRegion` when the library no longer knows the region.
    """
    company = {day.date: day.name for day in contract.company_holidays if start <= day.date <= end}
    not_given = set(contract.holidays_not_given)
    found: list[Holiday] = []
    given_by_region: set[date] = set()
    if contract.holiday_country is not None:
        region = named_holidays_between(
            contract.holiday_country, contract.holiday_subdivision, start, end
        )
        for day, name in region.items():
            given = day not in not_given
            if given:
                given_by_region.add(day)
            if given or include_not_given:
                found.append(Holiday(date=day, name=name, source=HolidaySource.REGION, given=given))
    for day, name in company.items():
        if day not in given_by_region:
            found.append(Holiday(date=day, name=name, source=HolidaySource.COMPANY, given=True))
    # On a date listed twice the region's row, not given, comes first.
    return sorted(found, key=lambda h: (h.date, h.given))


def contract_holidays(
    contract: Contract, start: date, end: date, *, company_name: str | None = None
) -> dict[date, str]:
    """The days within [start, end] the contract treats as holidays, by name —
    the set every week figure is computed from. With `company_name`, every
    company day goes by that name rather than the one typed for it: the
    timesheet, which the employer reads, carries no text the user typed."""

    def name(holiday: Holiday) -> str:
        if company_name is not None and holiday.source is HolidaySource.COMPANY:
            return company_name
        return holiday.name

    return {h.date: name(h) for h in contract_calendar(contract, start, end) if h.given}


@cache
def _year(country: str, subdivision: str | None, year: int) -> dict[date, str]:
    """One region's calendar for one year, built once per process.

    The balance reads every year since a contract started on every request,
    and some regions take ~10 ms a year to build; a mapping per
    (region, year) is a few hundred bytes, so the cache stays small.
    """
    try:
        calendar = holidays_lib.country_holidays(
            country, subdiv=subdivision, years=year, language=_language(country)
        )
    except NotImplementedError:
        # The region passed `check_region` when the contract was written; a
        # library upgrade can still stop knowing it. Surface that as the
        # domain's own error so the caller can decide what one bad contract
        # costs — the week route reports it, the project index skips it.
        raise UnknownHolidayRegion(country, subdivision) from None
    return dict(calendar.items())


@cache
def _language(country: str) -> str | None:
    """The language to name the region's holidays in: English where the
    library has it, the region's own default otherwise.

    An English-speaking region keeps its own English; the library names no
    default only for those, and offers no translations there.
    """
    calendar = holidays_lib.country_holidays(country)
    default = calendar.default_language
    if default is None or default.startswith("en"):
        return default
    return "en_US" if "en_US" in calendar.supported_languages else default


def check_region(country: str, subdivision: str | None) -> None:
    """Raise `UnknownHolidayRegion` unless the library knows the country and,
    when one is given, the subdivision."""
    subdivisions = _subdivisions_by_country().get(country)
    if subdivisions is None or (subdivision is not None and subdivision not in subdivisions):
        raise UnknownHolidayRegion(country, subdivision)


@cache
def regions() -> list[Region]:
    """Every supported country with its subdivisions, sorted by name.

    Cached because the list is static for the life of the process and building
    it instantiates one calendar per country.
    """
    names = {
        alpha2: _display_name(module) for module, (_, alpha2, *_) in registry.COUNTRIES.items()
    }
    result = [
        Region(
            code=code,
            name=names.get(code, code),
            subdivisions=_subdivisions_of(code, codes),
        )
        for code, codes in _subdivisions_by_country().items()
    ]
    result.sort(key=lambda region: region.name)
    return result


@cache
def _subdivisions_by_country() -> dict[str, list[str]]:
    return holidays_lib.list_supported_countries(include_aliases=False)


def _subdivisions_of(country: str, codes: list[str]) -> list[Subdivision]:
    # The library keeps human names only as aliases pointing at the code
    # ("Zürich" -> "ZH"). The first alias listed is the primary name; a
    # subdivision without one is shown by its code.
    aliases = holidays_lib.country_holidays(country).subdivisions_aliases
    names: dict[str, str] = {}
    for alias, code in aliases.items():
        names.setdefault(code, alias)
    return [Subdivision(code=code, name=names.get(code, code)) for code in codes]


_SMALL_WORDS = frozenset({"and", "of", "the"})


def _display_name(module_name: str) -> str:
    """`united_kingdom` -> `United Kingdom`, `isle_of_man` -> `Isle of Man`."""
    words = module_name.split("_")
    return " ".join(
        word if index and word in _SMALL_WORDS else word.capitalize()
        for index, word in enumerate(words)
    )
