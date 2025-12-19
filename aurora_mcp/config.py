from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """MCP Server settings loaded from environment variables"""

    database_url: str = Field(
        "postgresql+asyncpg://shenshunan:@localhost:5432/AuroraKB",
        alias="DATABASE_URL",
    )

    # Embedding settings
    embedding_provider: str = Field("openai", alias="EMBEDDING_PROVIDER")
    embedding_model: str = Field("text-embedding-v4", alias="EMBEDDING_MODEL")
    embedding_dimension: int = Field(1536, alias="EMBEDDING_DIMENSION")
    openai_api_key: str | None = Field("sk-**", alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field("https://api.openai.com/v1")

    # Search Optimization Phase 2: Query Expansion (optional, auto-enabled if model configured)
    query_expansion_model: str | None = Field(None, alias="QUERY_EXPANSION_MODEL")
    query_expansion_base_url: str | None = Field(None, alias="QUERY_EXPANSION_BASE_URL")
    query_expansion_api_key: str | None = Field(None, alias="QUERY_EXPANSION_API_KEY")
    query_expansion_temperature: float = Field(0.3, alias="QUERY_EXPANSION_TEMPERATURE")
    query_expansion_max_tokens: int = Field(50, alias="QUERY_EXPANSION_MAX_TOKENS")

    # Search Optimization Phase 3: Reranking (optional, auto-enabled if model configured)
    reranking_model: str | None = Field(None, alias="RERANKING_MODEL")
    reranking_base_url: str | None = Field(None, alias="RERANKING_BASE_URL")
    reranking_api_key: str | None = Field(None, alias="RERANKING_API_KEY")
    reranking_temperature: float = Field(0.0, alias="RERANKING_TEMPERATURE")
    reranking_max_tokens: int = Field(100, alias="RERANKING_MAX_TOKENS")
    reranking_top_k: int = Field(10, alias="RERANKING_TOP_K")

    # General settings
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
