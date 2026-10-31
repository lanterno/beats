"""Retention of an organisation's working-time record.

The decided shape (docs/organisations.md, stage 4 — retention, 2026-10-28):
a per-organisation period in years over a **statutory floor by
jurisdiction**, counted from each record's date. A setting below the floor
of the organisation's country is refused at write time
(`RETENTION_BELOW_FLOOR`), and an organisation that sets nothing keeps the
default — or its country's floor, where the law asks for longer than the
default does. What the record is actually kept for is
`effective_retention_years`, never the stored field: the write-time refusal
only ever sees a period somebody typed.
Nothing in here deletes: the enforcement is the operator-run purge
(`infrastructure/retention.py`, `scripts/retention_purge.py`), so the
setting never promises what no machinery honours — and during the beta the
purge is run by nobody.

The floors are the working-time statutes' own, verified October 2026:
Spain keeps the register four years (art. 34.9 ET); Germany two
(§16(2) ArbZG — the June 2026 reform draft keeps the figure); France and
Austria one; the Netherlands 52 weeks, rounded up to a year here; Poland
holds working-time records in the employee file for ten years after the
employment. A country this table does not know — and an organisation
without one — takes the strictest common floor, Spain's four years, so a
gap in the table can never allow deleting below a law we simply had not
written down. The CNIL treats five years as a ceiling for time-clock data,
which is a reason to keep the default at the floor, not above it.
"""

from datetime import date

RETENTION_FLOOR_YEARS: dict[str, int] = {
    "ES": 4,  # art. 34.9 Estatuto de los Trabajadores
    "DE": 2,  # §16(2) ArbZG
    "FR": 1,  # Code du travail art. D3171-16
    "AT": 1,  # §26 AZG
    "NL": 1,  # Arbeidstijdenwet: 52 weeks
    "PL": 10,  # Kodeks pracy: the employee file, employment + 10 years
}

DEFAULT_RETENTION_YEARS = 4


def retention_floor(country: str | None) -> int:
    """The fewest years an organisation in `country` may keep its record."""
    if country is None:
        return DEFAULT_RETENTION_YEARS
    return RETENTION_FLOOR_YEARS.get(country.upper(), DEFAULT_RETENTION_YEARS)


def retention_years(stored: int | None) -> int:
    """What an organisation's stored setting means: unset is the default."""
    return stored if stored is not None else DEFAULT_RETENTION_YEARS


def effective_retention_years(stored: int | None, country: str | None) -> int:
    """How long the record is actually kept: the setting, never under the floor.

    A stored period is refused below the floor when it is written, so it is
    the organisation that stored *nothing* this guards: the default is four
    years, which is under Poland's ten. Reading the stored field instead
    would purge such an organisation six years early — below a law we had
    written down.
    """
    return max(retention_years(stored), retention_floor(country))


def retention_cutoff(today: date, years: int) -> date:
    """The first day still kept: records dated before it have expired.

    A leap day's anniversary lands on 1 March, which errs toward keeping
    one day more, never less.
    """
    try:
        return today.replace(year=today.year - years)
    except ValueError:  # 29 February, years back has no 29th
        return date(today.year - years, 3, 1)
