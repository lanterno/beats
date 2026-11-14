"""The ids a command takes, checked when its arguments are parsed.

A document id is 24 characters of 0-9 and a-f. Anything else used to reach
`ObjectId()` in a repository and answer 500, or a 404 that read as "no such
thing" when the thing was a typo; checked here it is a 422 naming the box
(`InvalidCommandArgs`, beats/operator/commands.py). Kept lower-case, as every
page shows it, because a subject is matched by its id exactly — one queued job
per command and subject, erasure's sweep over `user_id`, the requests an
erasure closes — and an id typed in capitals must not become a second subject.

A module of its own so that commands.py and erasure_requests.py, which
commands.py imports for its registry, can both use it.
"""

import re
from typing import Annotated

from pydantic import AfterValidator


def _whole_id(value: str) -> str:
    value = value.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{24}", value):
        raise ValueError("an id is 24 characters of 0-9 and a-f; paste it whole")
    return value


DocumentId = Annotated[str, AfterValidator(_whole_id)]
