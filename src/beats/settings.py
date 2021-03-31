from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    db_dsn: str = Field(..., env='DB_DSN')
    db_name: str = Field(default="ptc", env='DB_NAME')
    access_token: str = Field(default="secret", env="ACCESS_TOKEN")


settings = Settings()
