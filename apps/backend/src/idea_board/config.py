from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="IDEA_BOARD_",
        env_file=".env",
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: SecretStr
    database_pool_size: Annotated[int, Field(gt=0)] = 5
    database_pool_timeout_seconds: Annotated[float, Field(gt=0)] = 2
    database_connect_timeout_seconds: Annotated[int, Field(gt=0)] = 3
    database_statement_timeout_ms: Annotated[int, Field(gt=0)] = 3000

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        try:
            database_url = make_url(value.get_secret_value())
        except (ArgumentError, ValueError):
            raise ValueError("Use a valid PostgreSQL connection URL") from None

        if (
            database_url.drivername not in {"postgresql", "postgresql+psycopg"}
            or not database_url.host
            or not database_url.username
            or not database_url.database
            or (database_url.port is not None and not 1 <= database_url.port <= 65535)
        ):
            raise ValueError("Use a PostgreSQL URL with a host, username, and database")

        return SecretStr(
            database_url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)
        )
