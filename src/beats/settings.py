from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    db_dsn: str = Field(..., env='DB_DSN')


settings = Settings()
