from pydantic import BaseSettings

USERNAME: str = "timekeeper"
PASSWORD: str = "foresthunt"
SERVER_URL: str = "ptc-akb5a.gcp.mongodb.net"
DB_NAME: str = "ptc"


class Settings(BaseSettings):
    db_dsn: str = f"mongodb+srv://{USERNAME}:{PASSWORD}@{SERVER_URL}/{DB_NAME}?retryWrites=true&w=majority"


settings = Settings()
