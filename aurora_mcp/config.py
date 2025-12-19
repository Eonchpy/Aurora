from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """MCP Server settings loaded from environment variables"""

    database_url: str = Field(
        "postgresql+asyncpg://shenshunan:@localhost:5432/AuroraKB",
        alias="DATABASE_URL",
    )

    embedding_provider: str = Field("openai", alias="EMBEDDING_PROVIDER")
    embedding_model: str = Field("text-embedding-v4", alias="EMBEDDING_MODEL")
    embedding_dimension: int = Field(1536, alias="EMBEDDING_DIMENSION")
    openai_api_key: str | None = Field("sk-**", alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field("https://api.openai.com/v1")

    max_content_length: int = Field(32000, alias="MAX_CONTENT_LENGTH")
    default_namespace: str = Field("default", alias="DEFAULT_NAMESPACE")

    model_config = SettingsConfigDict(
        env_file=(".env", "config/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
