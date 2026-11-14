"""The judgements the operator's pages are sent rather than make
(docs/backoffice.md § The pages, Trust and safety)."""

import pytest

from beats.operator.reads import SIGNUP_WAVE_MIN, signups_above_usual


@pytest.mark.parametrize(
    ("completed", "usual", "above"),
    [
        # Trust said "more than usual" for one sign-up against none.
        (1, 0, False),
        (SIGNUP_WAVE_MIN - 1, 0, False),
        (SIGNUP_WAVE_MIN, 0, True),
        # Twice the usual is enough; a median of a half counts as such.
        (9, 4.5, True),
        (19, 10, False),
        (20, 10, True),
        (4, 4, False),
    ],
)
def test_an_hour_is_above_usual_from_the_floor_and_twice_the_usual(completed, usual, above):
    assert signups_above_usual(completed, usual) is above
