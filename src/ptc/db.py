import pymongo

from .settings import settings


client = pymongo.MongoClient(settings.db_dsn + "/ptc" + "?retryWrites=true&w=majority")
db = client.ptc
