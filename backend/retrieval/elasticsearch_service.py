from typing import List, Dict, Any, Optional

import structlog
from elasticsearch import AsyncElasticsearch

from config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "document_id":      {"type": "keyword"},
            "document_name":    {"type": "text", "analyzer": "english"},
            "content":          {"type": "text", "analyzer": "english"},
            "section_heading":  {"type": "text", "analyzer": "english"},
            "chunk_type":       {"type": "keyword"},
            "page_number":      {"type": "integer"},
            "department":       {"type": "keyword"},
            "confidentiality":  {"type": "keyword"},
        }
    },
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
}


class ElasticsearchService:
    """Elasticsearch BM25 keyword search service."""

    def __init__(self):
        self.client = AsyncElasticsearch(
            [f"http://{settings.elasticsearch_host}:{settings.elasticsearch_port}"]
        )
        self.index = settings.elasticsearch_index_name

    async def ensure_index(self):
        """Create index if it doesn't exist."""
        exists = await self.client.indices.exists(index=self.index)
        if not exists:
            await self.client.indices.create(index=self.index, body=INDEX_MAPPING)
            logger.info("Elasticsearch index created", index=self.index)

    async def bulk_index(self, docs: List[Dict[str, Any]]):
        """Bulk index documents into Elasticsearch."""
        await self.ensure_index()
        operations = []
        for doc in docs:
            doc_id = doc.pop("id")
            operations.append({"index": {"_index": self.index, "_id": doc_id}})
            operations.append(doc)

        if operations:
            await self.client.bulk(body=operations, refresh=True)
            logger.info("Bulk indexed to Elasticsearch", count=len(docs))

    async def search(
        self,
        query: str,
        top_k: int = 50,
        department: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """BM25 keyword search."""
        await self.ensure_index()

        must_clauses = [
            {
                "multi_match": {
                    "query": query,
                    "fields": ["content^2", "document_name^1.5", "section_heading^1.2"],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            }
        ]

        filter_clauses = []
        if department and department != "all":
            filter_clauses.append({"term": {"department": department}})

        body = {
            "query": {
                "bool": {
                    "must": must_clauses,
                    "filter": filter_clauses,
                }
            },
            "size": top_k,
            "_source": True,
        }

        result = await self.client.search(index=self.index, body=body)
        hits = result["hits"]["hits"]

        return [
            {
                "id": h["_id"],
                "score": h["_score"],
                "content": h["_source"].get("content", ""),
                "document_id": h["_source"].get("document_id", ""),
                "document_name": h["_source"].get("document_name", ""),
                "page_number": h["_source"].get("page_number", 1),
                "section_heading": h["_source"].get("section_heading", ""),
                "chunk_type": h["_source"].get("chunk_type", "text"),
                "department": h["_source"].get("department", ""),
            }
            for h in hits
        ]

    async def bulk_delete(self, ids: List[str]):
        """Delete documents from Elasticsearch by IDs."""
        operations = [
            {"delete": {"_index": self.index, "_id": doc_id}}
            for doc_id in ids
        ]
        if operations:
            await self.client.bulk(body=operations, refresh=True)
            logger.info("Deleted from Elasticsearch", count=len(ids))

    async def health_check(self) -> bool:
        try:
            info = await self.client.cluster.health()
            return info["status"] in ("green", "yellow")
        except Exception:
            return False


_es_service = None


def get_es_service() -> ElasticsearchService:
    global _es_service
    if _es_service is None:
        _es_service = ElasticsearchService()
    return _es_service
