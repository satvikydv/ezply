from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./data/ezply.db"
    greenhouse_boards: str = ""
    lever_boards: str = ""
    ashby_boards: str = ""
    workable_boards: str = ""
    llm_provider: str = "openai"  # "openai" or "gemini"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = ""

    model_config = SettingsConfigDict(env_prefix="EZPLY_", env_file=".env", extra="ignore")

    def greenhouse_board_list(self) -> list[str]:
        boards = [board.strip() for board in self.greenhouse_boards.split(",")]
        return [board for board in boards if board]

    def lever_board_list(self) -> list[str]:
        boards = [board.strip() for board in self.lever_boards.split(",")]
        return [board for board in boards if board]

    def ashby_board_list(self) -> list[str]:
        boards = [board.strip() for board in self.ashby_boards.split(",")]
        return [board for board in boards if board]

    def workable_board_list(self) -> list[str]:
        boards = [board.strip() for board in self.workable_boards.split(",")]
        return [board for board in boards if board]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
