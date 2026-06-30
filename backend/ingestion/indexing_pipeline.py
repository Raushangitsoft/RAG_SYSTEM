import uuid
from datetime import datetime
from typing import List

import structlog
import tiktoken
from sqlalchemy.ext.asyncio import AsyncSession

from ingestion.document_parser import get_document_parser, ParsedChunk
from retrieval.qdrant_service import get_qdrant_service
from retrieval.elasticsearch_service import get_es_service
from services.embedding_service import get_embedding_service
from models.database import Document, Chunk
from config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


def count_tokens(text: str) -> int:
    try:
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


class IndexingPipeline:
    """Full document ingestion: parse → embed → index into Qdrant + Elasticsearch."""

    def __init__(self):
        self.parser = get_document_parser()
        self.embedding_service = get_embedding_service()
        self.qdrant_service = get_qdrant_service()
        self.es_service = get_es_service()

    async def run(self, db: AsyncSession, document: Document) -> bool:
        """
        Run the full indexing pipeline for a document.
        Returns True on success, False on failure.
        """
        logger.info("Starting indexing pipeline", doc_id=str(document.id), name=document.name)

        try:
            # Update status to processing
            document.status = "processing"
            await db.commit()

            # 1. Parse document
            chunks = await self.parser.parse(document.file_path)
            if not chunks:
                raise ValueError("No content extracted from document")

            # 2. Generate embeddings in batches
            texts = [c.content for c in chunks]
            embeddings = await self.embedding_service.embed_texts(texts)

            # 3. Build chunk records
            chunk_records = []
            qdrant_points = []
            es_docs = []

            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                chunk_id = str(uuid.uuid4())
                token_count = count_tokens(chunk.content)

                # DB record
                db_chunk = Chunk(
                    id=uuid.UUID(chunk_id),
                    document_id=document.id,
                    chunk_index=i,
                    content=chunk.content,
                    page_number=chunk.page_number,
                    section_heading=chunk.section_heading,
                    chunk_type=chunk.chunk_type,
                    token_count=token_count,
                    qdrant_id=chunk_id,
                    es_id=chunk_id,
                )
                chunk_records.append(db_chunk)

                # Qdrant payload
                qdrant_points.append({
                    "id": chunk_id,
                    "vector": embedding,
                    "payload": {
                        "chunk_id": chunk_id,
                        "document_id": str(document.id),
                        "document_name": document.name,
                        "content": chunk.content,
                        "page_number": chunk.page_number,
                        "section_heading": chunk.section_heading,
                        "chunk_type": chunk.chunk_type,
                        "department": document.department,
                        "confidentiality": document.confidentiality,
                    },
                })

                # Elasticsearch doc
                es_docs.append({
                    "id": chunk_id,
                    "document_id": str(document.id),
                    "document_name": document.name,
                    "content": chunk.content,
                    "page_number": chunk.page_number,
                    "section_heading": chunk.section_heading,
                    "chunk_type": chunk.chunk_type,
                    "department": document.department,
                    "confidentiality": document.confidentiality,
                })

            # 4. Index into Qdrant
            await self.qdrant_service.upsert_points(qdrant_points)

            # 5. Index into Elasticsearch
            await self.es_service.bulk_index(es_docs)

            # 6. Save chunks to PostgreSQL
            db.add_all(chunk_records)

            # 7. Update document record
            document.status = "indexed"
            document.chunk_count = len(chunk_records)
            document.indexed_at = datetime.utcnow()
            await db.commit()

            logger.info(
                "Indexing complete",
                doc_id=str(document.id),
                chunks=len(chunk_records),
            )
            return True

        except Exception as e:
            logger.error("Indexing pipeline failed", doc_id=str(document.id), error=str(e))
            document.status = "failed"
            document.error_message = str(e)
            await db.commit()
            return False

    async def delete_document_from_indexes(self, document: Document):
        """Remove all chunks from Qdrant and Elasticsearch."""
        chunk_ids = [str(c.qdrant_id) for c in document.chunks if c.qdrant_id]
        if chunk_ids:
            await self.qdrant_service.delete_points(chunk_ids)
            await self.es_service.bulk_delete(chunk_ids)
        logger.info("Document removed from indexes", doc_id=str(document.id))


_pipeline = None


def get_indexing_pipeline() -> IndexingPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = IndexingPipeline()
    return _pipeline
