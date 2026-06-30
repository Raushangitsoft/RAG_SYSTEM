import asyncio
import hashlib
from typing import List
from functools import lru_cache

import structlog
from FlagEmbedding import FlagModel

from config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


class EmbeddingService:
    """Singleton embedding service using BAAI/bge-m3 locally."""

    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load_model(self):
        if self._model is None:
            logger.info("Loading embedding model", model=settings.embedding_model)
            self._model = FlagModel(
                settings.embedding_model,
                use_fp16=False,  # CPU - use fp32
                cache_dir=f"{settings.models_base_path}/embeddings",
            )
            logger.info("Embedding model loaded successfully")

    def get_model(self) -> FlagModel:
        if self._model is None:
            self.load_model()
        return self._model

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts. Runs in thread pool to avoid blocking."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._embed_sync, texts)

    def _embed_sync(self, texts: List[str]) -> List[List[float]]:
        model = self.get_model()
        embeddings = model.encode(
            texts,
            batch_size=settings.embedding_batch_size,
            max_length=512,
        )
        return embeddings.tolist()

    async def embed_query(self, query: str) -> List[float]:
        """Embed a single query string."""
        embeddings = await self.embed_texts([query])
        return embeddings[0]

    @staticmethod
    def get_text_hash(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()


@lru_cache()
def get_embedding_service() -> EmbeddingService:
    service = EmbeddingService()
    service.load_model()
    return service
