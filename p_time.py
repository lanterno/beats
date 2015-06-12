# handles time
import time
from datetime import datetime


class Time(object):

    def __init__(self):
        self.set_string(time.ctime().split()[-2])

    def set_string(self, string):
        if string is None:
            pass
        else:
            time = list(map(int, string.split(":")))
            self.seconds = time[2]
            self.minutes = time[1]
            self.hours = time[0]

    def __str__(self):
        return "{}:{}:{}".format(self.hours, self.minutes, self.seconds)

    def set_seconds(self, seconds):
        self.hours = int(seconds/3600)
        self.minutes = int(seconds/60) - self.hours*60
        self.seconds = seconds % 60

    def get_seconds(self):
        return self.hours*3600 + self.minutes*60 + self.seconds

    def add_time(self, time):
        self.set_seconds(self.get_seconds() + time.get_seconds())

    def minues(self, other_time):
        t = Time()
        seconds = abs(self.get_seconds() - other_time.get_seconds())
        t.set_seconds(seconds)
        return t

    def date(cls):
        return str(datetime.now().date())
