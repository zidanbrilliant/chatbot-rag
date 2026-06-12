from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All fields match environment variables case-insensitively.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────
    app_env: str = Field("development")

    # ── Database ─────────────────────────────────────────
    database_url: str = Field("postgresql://postgres:postgres@db:5432/chatbot")

    # ── Qdrant ──────────────────────────────────────────
    qdrant_host: str = Field("qdrant")
    qdrant_port: int = Field(6333)
    qdrant_url: str = Field("http://qdrant:6333")
    qdrant_grpc_port: int = Field(6334)
    qdrant_collection: str = Field("company_knowledge_base")

    # ── Groq ─────────────────────────────────────────────
    groq_api_key: str = Field("", description="REQUIRED for Groq provider")
    groq_model: str = Field("llama-3.3-70b-versatile")

    # ── LLM Provider ──────────────────────────────────────
    llm_provider: str = Field("ollama", description="ollama | groq")
    ollama_llm_model: str = Field("qwen2.5:7b")

    # ── Ollama / Embedding ───────────────────────────────
    ollama_base_url: str = Field("http://host.docker.internal:11434")
    embedding_model: str = Field("bge-m3")
    embedding_dim: int = Field(1024)

    # ── RAG Pipeline ────────────────────────────────────
    similarity_threshold: float = Field(0.55)
    top_k: int = Field(5)
    chunk_size: int = Field(200)
    chunk_overlap: int = Field(25)
    hybrid_top_k: int = Field(20)
    max_query_length: int = Field(2000)

    # ── Session ──────────────────────────────────────────
    session_timeout_minutes: int = Field(30)
    session_max_turns: int = Field(10)
    max_history_turns: int = Field(10)
    session_cleanup_interval: int = Field(300)

    # ── Upload ───────────────────────────────────────────
    max_file_size_mb: int = Field(50)
    data_dir: str = Field("/data")

    # ── Google Fallback ──────────────────────────────────
    google_api_key: str = Field("")
    google_cse_id: str = Field("")
    enable_external_fallback: bool = Field(False)

    # ── Web Search (Hybrid RAG) ─────────────────────────
    enable_web_search: bool = Field(True)
    search_provider: str = Field("duckduckgo", description="search provider (only duckduckgo supported)")
    search_max_results: int = Field(5)
    search_timeout: int = Field(10)
    search_cache_ttl: int = Field(3600)

    # ── CORS ─────────────────────────────────────────────
    cors_origins: str = Field("http://localhost:3000,http://localhost:5173")

    # ── Rate Limit ───────────────────────────────────────
    rate_limit_window: int = Field(60)
    rate_limit_chat_max: int = Field(30)
    rate_limit_admin_max: int = Field(15)
    rate_limit_cleanup_interval: int = Field(300)

    # ── Security ─────────────────────────────────────────
    jwt_secret_key: str = Field("")
    admin_api_key: str = Field("supersecret")

    # ── Redis ────────────────────────────────────────────
    redis_url: str = Field("redis://localhost:6379/0")

    # ── Legacy compat aliases (keep UPPER_SNAKE_CASE exports working) ──
    vector_size: int = Field(1024)

    def validate_required(self) -> list[str]:
        """Check critical env vars. Returns list of missing keys."""
        missing: list[str] = []
        if self.app_env != "test" and self.llm_provider == "groq" and not self.groq_api_key:
            missing.append("GROQ_API_KEY (required when LLM_PROVIDER=groq)")
        return missing


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton — loaded once at first call."""
    return Settings()


# Eager load so invalid config fails at startup
_settings = get_settings()


# ── Backward-compatible UPPER_CASE re-exports ──────────
# The existing codebase imports from app.config using UPPER_CASE names.
# Re-export them here so nothing breaks.

APP_ENV = _settings.app_env
DATABASE_URL = _settings.database_url
QDRANT_HOST = _settings.qdrant_host
QDRANT_PORT = _settings.qdrant_port
QDRANT_URL = _settings.qdrant_url
QDRANT_GRPC_PORT = _settings.qdrant_grpc_port
QDRANT_COLLECTION = _settings.qdrant_collection
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
HYBRID_TOP_K = _settings.hybrid_top_k
MAX_QUERY_LENGTH = _settings.max_query_length
SESSION_TIMEOUT_MINUTES = _settings.session_timeout_minutes
SESSION_MAX_TURNS = _settings.session_max_turns
MAX_HISTORY_TURNS = _settings.max_history_turns
SESSION_CLEANUP_INTERVAL = _settings.session_cleanup_interval
MAX_FILE_SIZE_MB = _settings.max_file_size_mb
DATA_DIR = _settings.data_dir
GOOGLE_API_KEY = _settings.google_api_key
GOOGLE_CSE_ID = _settings.google_cse_id
ENABLE_EXTERNAL_FALLBACK = _settings.enable_external_fallback
CORS_ORIGINS = _settings.cors_origins
RATE_LIMIT_WINDOW = _settings.rate_limit_window
RATE_LIMIT_MAX = _settings.rate_limit_chat_max  # legacy alias
RATE_LIMIT_CHAT_MAX = _settings.rate_limit_chat_max
RATE_LIMIT_ADMIN_MAX = _settings.rate_limit_admin_max
RATE_LIMIT_CLEANUP_INTERVAL = _settings.rate_limit_cleanup_interval
ADMIN_RATE_LIMIT_MAX = _settings.rate_limit_admin_max  # legacy alias
JWT_SECRET_KEY = _settings.jwt_secret_key
ADMIN_API_KEY = _settings.admin_api_key
REDIS_URL = _settings.redis_url
VECTOR_SIZE = _settings.vector_size
MAX_HISTORY_TURNS = _settings.max_history_turns
ENABLE_WEB_SEARCH = _settings.enable_web_search
SEARCH_PROVIDER = _settings.search_provider
SEARCH_MAX_RESULTS = _settings.search_max_results
SEARCH_TIMEOUT = _settings.search_timeout
SEARCH_CACHE_TTL = _settings.search_cache_ttl

