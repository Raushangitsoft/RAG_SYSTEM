from typing import List, Dict, Any, Optional
from collections import defaultdict

import structlog

from retrieval.qdrant_service import get_qdrant_service
from retrieval.elasticsearch_service import get_es_service
from services.embedding_service import get_embedding_service
from config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


def reciprocal_rank_fusion(
    results_list: List[List[Dict]],
    k: int = 60,
) -> List[Dict]:
    """
    Reciprocal Rank Fusion (RRF) for merging ranked lists.
    RRF score = sum(1 / (k + rank)) across all lists.
    """
    scores: Dict[str, float] = defaultdict(float)
    docs: Dict[str, Dict] = {}

    for results in results_list:
        for rank, doc in enumerate(results, start=1):
            doc_id = doc["id"]
            scores[doc_id] += 1.0 / (k + rank)
            if doc_id not in docs:
                docs[doc_id] = doc

    fused = [
        {**docs[doc_id], "rrf_score": score}
        for doc_id, score in sorted(scores.items(), key=lambda x: x[1], reverse=True)
    ]
    return fused


class HybridSearchService:
    """Combines BM25 (Elasticsearch) and dense vector (Qdrant) search with RRF fusion."""

    def __init__(self):
        self.qdrant = get_qdrant_service()
        self.es = get_es_service()
        self.embedding_service = get_embedding_service()

    async def search(
        self,
        query: str,
        top_k: int = None,
        department: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search: BM25 + dense vector → RRF fusion.
        """
        top_k = top_k or settings.hybrid_search_top_k

        # Embed the query for vector search
        query_vector = await self.embedding_service.embed_query(query)

        # Run both searches in parallel
        import asyncio
        vector_results, bm25_results = await asyncio.gather(
            self.qdrant.search(query_vector, top_k=top_k, department=department),
            self.es.search(query, top_k=top_k, department=department),
        )

        logger.info(
            "Hybrid search complete",
            vector_results=len(vector_results),
            bm25_results=len(bm25_results),
        )

        # Fuse with RRF
        fused = reciprocal_rank_fusion([vector_results, bm25_results])
        return fused[:top_k]


_hybrid_search = None


def get_hybrid_search() -> HybridSearchService:
    global _hybrid_search
    if _hybrid_search is None:
        _hybrid_search = HybridSearchService()
    return _hybrid_search
