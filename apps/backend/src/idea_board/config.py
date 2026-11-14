from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="IDEA_BOARD_",
        env_file=".env",
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: SecretStr
