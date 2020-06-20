from datetime import datetime

from ..engine import db_manager


def last_recorded_activity():
    logs = db_manager.logs()
    logs = sorted(logs, key=lambda log: log["start_time"])
    return logs[-1]