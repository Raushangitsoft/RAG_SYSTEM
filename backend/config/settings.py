from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List


class Settings(BaseSettings):
    # App
    app_name: str = "HybridRAG"
    app_env: str = "production"
    debug: bool = False
    log_level: str = "INFO"

    # PostgreSQL
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "raguser"
    postgres_password: str = "ragpassword"
    postgres_db: str = "ragdb"
    database_url: str = "postgresql+asyncpg://raguser:ragpassword@postgres:5432/ragdb"

    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_ttl_seconds: int = 3600

    # Qdrant
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_collection_name: str = "documents"

    # Elasticsearch
    elasticsearch_host: str = "elasticsearch"
    elasticsearch_port: int = 9200
    elasticsearch_index_name: str = "documents"

    # Ollama / LLM
    ollama_host: str = "ollama"
    ollama_port: int = 11434
    ollama_base_url: str = "http://ollama:11434"
    llm_model: str = "qwen2.5:7b-instruct-q4_K_M"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 2048
    llm_context_window: int = 8192

    # Embedding
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "cpu"
    embedding_batch_size: int = 8
    embedding_dimension: int = 1024

    # Reranker
    reranker_model: str = "BAAI/bge-reranker-large"
    reranker_device: str = "cpu"
    reranker_top_k: int = 10

    # Retrieval
    hybrid_search_top_k: int = 50
    bm25_weight: float = 0.45
    vector_weight: float = 0.55

    # Storage
    documents_base_path: str = "/app/data/documents"
    models_base_path: str = "/app/data/models"
    max_upload_size_mb: int = 100
    allowed_extensions: str = "pdf,docx,pptx,xlsx,txt"

    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 100

    # Security
    secret_key: str = "change-this-in-production"
    access_token_expire_minutes: int = 60

    @property
    def allowed_extensions_list(self) -> List[str]:
        return [e.strip().lower() for e in self.allowed_extensions.split(",")]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
