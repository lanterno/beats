"""Public holidays for a contract's region — the only importer of the `holidays` package.

Everything downstream takes holidays as a plain `set[date]`, so the arithmetic
in `contracts.py` never touches this module and the library is exchangeable
from one place. What is exposed: the dates in a range for one region, the
list of regions for a picker, and the check the project service runs on a
(country, subdivision) pair before a contract is written.

Codes are the library's own: ISO 3166-1 alpha-2 for the country and the
ISO 3166-2 part for the subdivision (`GB`/`ENG`, `CH`/`ZH`). Substitute days
— a Monday off for a Christmas that fell on a Sunday — come back as ordinary
holidays, which is exactly what the arithmetic wants: they are weekdays and
cost their day.
"""

from datetime import date
from functools import cache

import holidays as holidays_lib
from holidays import registry
from pydantic import BaseModel

from beats.domain.exceptions import UnknownHolidayRegion


class Subdivision(BaseModel):
    code: str
    name: str


class Region(BaseModel):
    """One country in the picker, with the subdivisions that change its calendar."""

    code: str  # ISO 3166-1 alpha-2
    name: str
    subdivisions: list[Subdivision]


def holidays_between(country: str, subdivision: str | None, start: date, end: date) -> set[date]:
    """Every public holiday in the region falling within [start, end]."""
    calendar = holidays_lib.country_holidays(
        country, subdiv=subdivision, years=range(start.year, end.year + 1)
    )
    return {day for day in calendar if start <= day <= end}


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
