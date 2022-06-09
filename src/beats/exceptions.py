class CanNotStopNonBeatingHeart(Exception):
    pass


class ProjectWasNotStarted(Exception):
    pass


class TwoProjectInProgess(Exception):
    pass


class ProjectAlreadyStarted(Exception):
    pass


class InconsistentEndTime(Exception):
    message = "End time must come after start time"


class NoObjectMatched(Exception):
    message = "The used filter didn't yield any records"
