from typing import List, Dict, Any, Optional

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter,
    FieldCondition, MatchValue, PointIdsList
)

from config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


class QdrantService:
    """Qdrant vector database service."""

    def __init__(self):
        self.client = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )
        self.collection = settings.qdrant_collection_name
        self.dimension = settings.embedding_dimension

    async def ensure_collection(self):
    
     collections = await self.client.get_collections()
     names = [c.name for c in collections.collections]
     if self.collection not in names:
        try:
            await self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=self.dimension,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("Qdrant collection created", collection=self.collection)
        except Exception as e:
            if "already exists" in str(e).lower() or "409" in str(e):
                logger.info("Qdrant collection already created by another worker", collection=self.collection)
            else:
                raise

    async def upsert_points(self, points: List[Dict[str, Any]]):
        """Upsert a batch of points into Qdrant."""
        await self.ensure_collection()
        structs = [
            PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
            for p in points
        ]
        # Batch in groups of 100
        batch_size = 100
        for i in range(0, len(structs), batch_size):
            await self.client.upsert(
                collection_name=self.collection,
                points=structs[i:i + batch_size],
            )
        logger.info("Upserted points", count=len(structs))

    async def search(
        self,
        query_vector: List[float],
        top_k: int = 50,
        department: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar vectors with optional department filter."""
        await self.ensure_collection()

        query_filter = None
        if department and department != "all":
            query_filter = Filter(
                must=[FieldCondition(key="department", match=MatchValue(value=department))]
            )

        results = await self.client.search(
            collection_name=self.collection,
            query_vector=query_vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )

        return [
            {
                "id": str(r.id),
                "score": r.score,
                "content": r.payload.get("content", ""),
                "document_id": r.payload.get("document_id", ""),
                "document_name": r.payload.get("document_name", ""),
                "page_number": r.payload.get("page_number", 1),
                "section_heading": r.payload.get("section_heading", ""),
                "chunk_type": r.payload.get("chunk_type", "text"),
                "department": r.payload.get("department", ""),
            }
            for r in results
        ]

    async def delete_points(self, ids: List[str]):
        """Delete points by IDs."""
        await self.client.delete(
            collection_name=self.collection,
            points_selector=PointIdsList(points=ids),
        )
        logger.info("Deleted points from Qdrant", count=len(ids))

    async def health_check(self) -> bool:
        try:
            await self.client.get_collections()
            return True
        except Exception:
            return False


_qdrant_service = None


def get_qdrant_service() -> QdrantService:
    global _qdrant_service
    if _qdrant_service is None:
        _qdrant_service = QdrantService()
    return _qdrant_service
