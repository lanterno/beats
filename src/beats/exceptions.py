class LogIsStopped(Exception):
    pass


class ProjectWasNotStarted(Exception):
    pass


class MoreThanOneLogOpenForProject(Exception):
    pass


class ProjectAlreadyStarted(Exception):
    pass


class InconsistentEndTime(Exception):
    message = "End time must come after start time"
