"""
This file provides the following functionality
- Data analysis for day vs backmarket work start time
"""
from dash_app.engine import db_manager
from datetime import date


def get_bm_start_times_graph_data():
    logs = db_manager.logs()
    logs = [log for log in logs if log["project"] == "backmarket"]  # Only backmarket projects
    for log in logs:
        log.update({"day": date.fromisoformat(log["date"]), "start_time": log["start_time"].time().hour})
    # logs = [log for log in logs if log["day"].month == 10]
    logs = [log for log in logs if 6 <= log["start_time"] <= 15]
    logs_as_dict = {}
    for log in logs:
        if log["day"] not in logs_as_dict:
            logs_as_dict[log["day"]] = log["start_time"]
            continue
        if log["start_time"] < logs_as_dict[log["day"]]:
            logs_as_dict[log["day"]] = log["start_time"]
    return list(logs_as_dict.keys()), list(logs_as_dict.values())
