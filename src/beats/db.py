import pymongo

from .settings import settings

# Treat DB_DSN as the full MongoDB connection string
client = pymongo.MongoClient(settings.db_dsn)
db = getattr(client, settings.db_name)
