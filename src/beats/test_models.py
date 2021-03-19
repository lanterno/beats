import pytest

from datetime import datetime
from beats.models import Beat

from beats.exceptions import InconsistentEndTime


class TestBeatModel:
    def test_beat_stop_timer(self):
        log = Beat(start=datetime.fromisoformat("2020-01-11T04:30:00"))
        log.stop_timer(datetime.fromisoformat("2020-01-11T04:30:00"))

        assert log.end == datetime.fromisoformat("2020-01-11T04:30:00")

    def test_end_time_can_not_be_after_start_time(self):
        log = Beat(start=datetime.fromisoformat("2021-01-11T01:00:00"))
        with pytest.raises(InconsistentEndTime):
            log.stop_timer(datetime.fromisoformat("2020-01-11T02:00:00"))

    def test_can_not_stop_time_when_already_stopped(self):
        pass

    def test_get_log_duration(self):
        pass
