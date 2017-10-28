# handles time
import time
from datetime import datetime


class Time(object):

    '''
    has 3 distinct attributes Hour, Minute, Second.
    Every new method or modification on old methods must work on them as
    the main properities that define the object.
    '''

    def __init__(self, str_time=None, sec_time=None):
        if str_time:
            self.set_string(str_time)
        elif sec_time or sec_time == 0:
            self.set_seconds(sec_time)
        else:
            self.set_string(time.ctime().split()[-2])

    def set_string(self, string):
        if string is None:
            return 0
        if string.startswith('Not'):
            print("WARNING: you have an unclosed time log.")
            print("This is you total time so far.")
            string = time.ctime().split()[-2]

        t = list(map(int, string.split(":")))
        self.seconds = t[2]
        self.minutes = t[1]
        self.hours = t[0]

    def __str__(self):
        return "{}:{}:{}".format(self.hours, self.minutes, self.seconds)

    def set_seconds(self, seconds):
        self.hours = int(seconds / 3600)
        self.minutes = int(seconds / 60) - self.hours * 60
        self.seconds = seconds % 60
        return self

    def get_seconds(self):
        return self.hours * 3600 + self.minutes * 60 + self.seconds

    def add_time(self, t):
        return self.set_seconds(self.get_seconds() + t.get_seconds())

    def minues(self, before):
        if self.greater_than(before):  # before midnight
            seconds = abs(self.get_seconds() - before.get_seconds())
            return self.set_seconds(seconds)
        else:                          # after midnight
            before_midnight = Time('24:00:00').minues(before)
            return self.add_time(before_midnight)

    def greater_than(self, time):
        return self.get_seconds() > time.get_seconds()

    def log_time(log):
        if log is None:
            print("No logs for this day")
            return 0
        start = Time(str_time=log['start'])
        end = Time(str_time=log['end'])
        end.minues(start)
        return end

    def date():
        # 'yyyy-mm-dd'
        return str(datetime.now().date())
