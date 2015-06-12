from p_time import Time


class Log(object):

    def __init__(self, start, end=None):
        self.start = Time()
        self.start.set_string(start)
        self.end = Time()
        self.set_string(end)
        self.date = "00/00/00"

    def stop(self):
        self.end.set_current_time()
