from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./data/ezply.db"
    greenhouse_boards: str = ""

    model_config = SettingsConfigDict(env_prefix="EZPLY_", env_file=".env", extra="ignore")

    def greenhouse_board_list(self) -> list[str]:
        boards = [board.strip() for board in self.greenhouse_boards.split(",")]
        return [board for board in boards if board]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
