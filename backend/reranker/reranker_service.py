import asyncio
from typing import List, Dict, Any
from functools import lru_cache

import structlog
from FlagEmbedding import FlagReranker

from config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


class RerankerService:
    """BGE cross-encoder reranker service."""

    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load_model(self):
        if self._model is None:
            logger.info("Loading reranker model", model=settings.reranker_model)
            self._model = FlagReranker(
                settings.reranker_model,
                use_fp16=False,  # CPU
                
            )
            logger.info("Reranker model loaded successfully")

    def get_model(self) -> FlagReranker:
        if self._model is None:
            self.load_model()
        return self._model

    async def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int = None,
    ) -> List[Dict[str, Any]]:
        """
        Rerank candidate chunks using cross-encoder scoring.
        Returns top_k candidates sorted by reranker score.
        """
        if not candidates:
            return candidates

        top_k = top_k or settings.reranker_top_k
        loop = asyncio.get_event_loop()
        scores = await loop.run_in_executor(
            None, self._score_sync, query, [c["content"] for c in candidates]
        )

        for candidate, score in zip(candidates, scores):
            candidate["reranker_score"] = float(score)

        reranked = sorted(candidates, key=lambda x: x["reranker_score"], reverse=True)
        return reranked[:top_k]

    def _score_sync(self, query: str, texts: List[str]) -> List[float]:
        model = self.get_model()
        pairs = [[query, text] for text in texts]
        scores = model.compute_score(pairs, normalize=True)
        if isinstance(scores, float):
            scores = [scores]
        return scores


@lru_cache()
def get_reranker_service() -> RerankerService:
    service = RerankerService()
    service.load_model()
    return service
