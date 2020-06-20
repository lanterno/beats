import pymongo

from .settings import settings


client = pymongo.MongoClient(settings.db_dsn)
db = client.ptc
