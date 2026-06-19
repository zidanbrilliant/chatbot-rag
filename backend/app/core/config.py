from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = Field("development")
    database_url: str = Field("postgresql://postgres:postgres@db:5432/chatbot")
    qdrant_host: str = Field("qdrant")
    qdrant_port: int = Field(6333)
    qdrant_collection: str = Field("company_knowledge_base")
    vector_size: int = Field(1024)
    groq_api_key: str = Field("", description="REQUIRED for Groq provider")
    groq_model: str = Field("llama-3.3-70b-versatile")
    llm_provider: str = Field("ollama", description="ollama | groq")
    ollama_llm_model: str = Field("qwen2.5:7b")
    ollama_base_url: str = Field("http://host.docker.internal:11434")
    embedding_model: str = Field("bge-m3")
    embedding_dim: int = Field(1024)
    similarity_threshold: float = Field(0.55)
    top_k: int = Field(5)
    chunk_size: int = Field(200)
    chunk_overlap: int = Field(25)
    hybrid_top_k: int = Field(20)
    max_query_length: int = Field(2000)
    session_timeout_minutes: int = Field(30)
    max_history_turns: int = Field(10)
    session_cleanup_interval: int = Field(300)
    max_file_size_mb: int = Field(50)
    data_dir: str = Field("/data")
    enable_web_search: bool = Field(True)
    search_max_results: int = Field(5)
    search_timeout: int = Field(10)
    search_cache_ttl: int = Field(3600)
    cors_origins: str = Field("http://localhost:3000,http://localhost:5173")
    rate_limit_window: int = Field(60)
    rate_limit_chat_max: int = Field(30)
    rate_limit_admin_max: int = Field(15)
    admin_api_key: str = Field("supersecret")
    redis_url: str = Field("redis://localhost:6379/0")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


_settings = get_settings()


APP_ENV = _settings.app_env
DATABASE_URL = _settings.database_url
QDRANT_HOST = _settings.qdrant_host
QDRANT_PORT = _settings.qdrant_port
QDRANT_COLLECTION = _settings.qdrant_collection
VECTOR_SIZE = _settings.vector_size
GROQ_API_KEY = _settings.groq_api_key
GROQ_MODEL = _settings.groq_model
LLM_PROVIDER = _settings.llm_provider
OLLAMA_LLM_MODEL = _settings.ollama_llm_model
OLLAMA_BASE_URL = _settings.ollama_base_url
EMBEDDING_MODEL = _settings.embedding_model
EMBEDDING_DIM = _settings.embedding_dim
SIMILARITY_THRESHOLD = _settings.similarity_threshold
TOP_K = _settings.top_k
CHUNK_SIZE = _settings.chunk_size
CHUNK_OVERLAP = _settings.chunk_overlap
MAX_QUERY_LENGTH = _settings.max_query_length
SESSION_TIMEOUT_MINUTES = _settings.session_timeout_minutes
MAX_HISTORY_TURNS = _settings.max_history_turns
SESSION_CLEANUP_INTERVAL = _settings.session_cleanup_interval
MAX_FILE_SIZE_MB = _settings.max_file_size_mb
DATA_DIR = _settings.data_dir
CORS_ORIGINS = _settings.cors_origins
RATE_LIMIT_WINDOW = _settings.rate_limit_window
RATE_LIMIT_CHAT_MAX = _settings.rate_limit_chat_max
RATE_LIMIT_ADMIN_MAX = _settings.rate_limit_admin_max
ADMIN_API_KEY = _settings.admin_api_key
REDIS_URL = _settings.redis_url
ENABLE_WEB_SEARCH = _settings.enable_web_search
SEARCH_MAX_RESULTS = _settings.search_max_results
SEARCH_TIMEOUT = _settings.search_timeout
SEARCH_CACHE_TTL = _settings.search_cache_ttl
