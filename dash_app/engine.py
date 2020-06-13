import os
from pymongo import MongoClient


class DBManager:
    def __init__(self):
        self.connection = MongoClient(os.getenv("MONGODB_URI"))
        if os.getenv("MONGODB_URI"):
            # This covers the case where DB name is provided in the URI
            self.db = self.connection.get_database()
        else:
            self.db = self.connection.ptc
        self.projects_collection = self.db['projects']

    def projects(self):
        return self.projects_collection.find()

    @staticmethod
    def serialize_log(log):

        start = log["start"]
        hour, minute, second = start.split(":")
        if len(hour) == 1:
            hour = "0" + hour
        if len(minute) == 1:
            minute = "0" + minute
        if len(second) == 1:
            second = "0" + second
        log["start"] = f"{hour}:{minute}:{second}"

        from datetime import datetime, timedelta
        start_time = datetime.fromisoformat("{}T{}".format(log["date"], log.pop("start")))
        log["start_time"] = start_time

        if log["end"] == "Not yet.":
            log["end_time"] = None
            return
        hour, minute, second = log["end"].split(":")
        if len(hour) == 1:
            hour = "0" + hour
        if len(minute) == 1:
            minute = "0" + minute
        if len(second) == 1:
            second = "0" + second
        log["end"] = f"{hour}:{minute}:{second}"
        end_time = datetime.fromisoformat("{}T{}".format(log["date"], log.pop("end")))
        if end_time < start_time:
            end_time += timedelta(days=1)
        log["end_time"] = end_time

    def logs(self):

        logs = []
        for project in self.projects():
            for log in project["logs"]:
                log["project"] = project["name"]
            logs.extend(project["logs"])
        for log in logs:
            self.serialize_log(log)
        return logs


db_manager = DBManager()
