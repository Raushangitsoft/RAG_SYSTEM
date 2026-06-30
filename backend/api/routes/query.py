from typing import Optional, List
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from pipelines.rag_pipeline import run_rag_pipeline
from models.database import QueryLog, get_db
from config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/query", tags=["query"])


class QueryRequest(BaseModel):
    query: str
    department: Optional[str] = None


class SourceRef(BaseModel):
    document_name: str
    document_id: str
    page_number: int
    section_heading: str
    score: float


class QueryResponse(BaseModel):
    query: str
    rewritten_query: str
    answer: str
    sources: List[SourceRef]
    latency_ms: int
    chunk_count: int
    from_cache: bool


class QueryLogResponse(BaseModel):
    id: str
    query: str
    answer: Optional[str]
    latency_ms: Optional[int]
    chunk_count: Optional[int]
    status: str
    created_at: str


@router.post("/", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db),
):
    """Run a RAG query and return answer with citations."""
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    if len(request.query) > 2000:
        raise HTTPException(status_code=400, detail="Query too long (max 2000 characters)")

    result = await run_rag_pipeline(
        query=request.query.strip(),
        department=request.department,
    )

    # Log the query
    log = QueryLog(
        query=result["query"],
        rewritten_query=result["rewritten_query"],
        answer=result["answer"],
        sources=result["sources"],
        latency_ms=result["latency_ms"],
        chunk_count=result["chunk_count"],
        model_used=settings.llm_model,
        status="error" if result.get("error") else "success",
    )
    db.add(log)
    await db.commit()

    return QueryResponse(
        query=result["query"],
        rewritten_query=result["rewritten_query"],
        answer=result["answer"],
        sources=[SourceRef(**s) for s in result["sources"]],
        latency_ms=result["latency_ms"],
        chunk_count=result["chunk_count"],
        from_cache=result["from_cache"],
    )


@router.get("/history", response_model=List[QueryLogResponse])
async def get_query_history(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Get recent query history."""
    result = await db.execute(
        select(QueryLog).order_by(desc(QueryLog.created_at)).limit(limit)
    )
    logs = result.scalars().all()
    return [
        QueryLogResponse(
            id=str(log.id),
            query=log.query,
            answer=log.answer,
            latency_ms=log.latency_ms,
            chunk_count=log.chunk_count,
            status=log.status,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]
