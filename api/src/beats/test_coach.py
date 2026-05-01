"""Pure unit tests for the coach domain.

Sibling of test_domain.py — covers the coach modules whose logic is
deterministic enough to test without spinning up Mongo or making LLM
calls. Heavier integration tests (gateway streaming with a fake client,
context builders against repo fakes) live here too as they're added.

The test_api.py suite covers the HTTP layer; this file covers the
modules underneath.
"""

from beats.coach.repos import fmt_minutes


class TestFmtMinutes:
    """fmt_minutes formats a minute count as 'Nh Mm' or 'Mm'.

    Used in the coach's session tables and the day/user context builders.
    Locks in the boundary cases — these are the inputs that matter for
    the coach's per-project hour summaries (a 60-minute session formatting
    as '60m' instead of '1h 0m' would surprise readers, and a fractional
    input formatting as '0h 0m' instead of '0m' would clutter the output).
    """

    def test_zero_minutes(self):
        assert fmt_minutes(0) == "0m"

    def test_under_one_hour(self):
        assert fmt_minutes(15) == "15m"
        assert fmt_minutes(45) == "45m"
        # Boundary — one minute under the hour.
        assert fmt_minutes(59) == "59m"

    def test_exactly_one_hour(self):
        # 60 → "1h 0m", not "60m" — the hour boundary kicks in at >= 60
        # because divmod(60, 60) == (1, 0) and the h>0 branch fires.
        assert fmt_minutes(60) == "1h 0m"

    def test_one_hour_with_remainder(self):
        assert fmt_minutes(61) == "1h 1m"
        assert fmt_minutes(75) == "1h 15m"
        assert fmt_minutes(90) == "1h 30m"

    def test_multiple_hours(self):
        assert fmt_minutes(120) == "2h 0m"
        assert fmt_minutes(125) == "2h 5m"
        assert fmt_minutes(480) == "8h 0m"

    def test_large_value(self):
        # 24h+ — the coach occasionally summarizes across multi-day
        # windows. No special handling for "1d", just keeps counting hours.
        assert fmt_minutes(1500) == "25h 0m"
        assert fmt_minutes(1543) == "25h 43m"

    def test_fractional_input_truncates(self):
        # int() truncates toward zero (per the implementation's
        # divmod(int(minutes), 60)). A 30.7-minute session reads as
        # "30m", not "31m" — pin so a future change to round() is
        # a deliberate decision, not an accident.
        assert fmt_minutes(30.7) == "30m"
        assert fmt_minutes(59.9) == "59m"
        # 60.5 → int → 60 → "1h 0m" (the hour kicks in only AT 60
        # post-truncation, not before).
        assert fmt_minutes(60.5) == "1h 0m"
