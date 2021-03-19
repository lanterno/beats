import pymongo

from .settings import settings


client = pymongo.MongoClient(f"{settings.db_dsn}/{settings.db_name}?retryWrites=true&w=majority")
db = getattr(client, settings.db_name)


