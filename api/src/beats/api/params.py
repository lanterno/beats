"""Query parameters shared by more than one router."""

import re
from datetime import date
from typing import Annotated

from fastapi import Query
from pydantic import BeforeValidator, WithJsonSchema

_MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])")


def _first_of_month(value: object) -> date:
    """'YYYY-MM' to the 1st of that month. Anything else — '2026-9', a full
    date, '0000-01', which `date` refuses — is a ValueError, which a query
    parameter turns into a 422 naming `month`."""
    if not isinstance(value, str) or _MONTH.fullmatch(value) is None:
        msg = "month must be YYYY-MM"
        raise ValueError(msg)
    return date(int(value[:4]), int(value[5:]), 1)


# The schema is the string a client sends, not the `date` it becomes. Left to
# pydantic it would come from `date` and say `format: date`: a full date, which
# `_first_of_month` refuses with a 422.
MonthQuery = Annotated[
    date,
    BeforeValidator(_first_of_month),
    Query(description="The month wanted, as YYYY-MM."),
    WithJsonSchema({"type": "string", "pattern": f"^{_MONTH.pattern}$", "examples": ["2026-09"]}),
]
