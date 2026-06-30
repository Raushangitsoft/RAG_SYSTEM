import uuid
from typing import List, Optional
from pathlib import Path

import structlog
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from models.database import Document, Chunk, get_db
from services.storage_service import get_storage_service
from services.cache_service import get_cache_service
from ingestion.indexing_pipeline import get_indexing_pipeline
from config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentResponse(BaseModel):
    id: str
    name: str
    original_name: str
    department: str
    owner: str
    tags: List[str]
    confidentiality: str
    version: int
    status: str
    chunk_count: int
    file_size: Optional[int]
    created_at: str
    indexed_at: Optional[str]

    class Config:
        from_attributes = True


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    department: str = Form(default="general"),
    owner: str = Form(default="system"),
    tags: str = Form(default=""),
    confidentiality: str = Form(default="internal"),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document and trigger background indexing."""
    # Validate extension
    ext = Path(file.filename).suffix.lstrip(".").lower()
    if ext not in settings.allowed_extensions_list:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Allowed: {settings.allowed_extensions}"
        )

    # Read file
    content = await file.read()
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(status_code=413, detail="File too large")

    storage = get_storage_service()

    # Check for duplicate via hash
    content_hash = await storage.compute_hash(content)
    existing = await db.execute(
        select(Document).where(Document.content_hash == content_hash)
    )
    existing_doc = existing.scalar_one_or_none()
    if existing_doc:
        raise HTTPException(
            status_code=409,
            detail=f"Document already exists: {existing_doc.name}"
        )

    # Create document record
    doc_id = uuid.uuid4()
    file_path, _ = await storage.save_file(
        content, department, str(doc_id), 1, file.filename
    )

    tags_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    document = Document(
        id=doc_id,
        name=Path(file.filename).stem,
        original_name=file.filename,
        file_path=file_path,
        file_size=len(content),
        mime_type=file.content_type,
        department=department,
        owner=owner,
        tags=tags_list,
        confidentiality=confidentiality,
        content_hash=content_hash,
        status="pending",
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    # Trigger background indexing
    background_tasks.add_task(_run_indexing, str(doc_id))

    logger.info("Document uploaded", doc_id=str(doc_id), name=file.filename)
    return _doc_to_response(document)


async def _run_indexing(doc_id: str):
    """Background task to run indexing pipeline."""
    from models.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
        document = result.scalar_one_or_none()
        if document:
            pipeline = get_indexing_pipeline()
            await pipeline.run(db, document)


@router.get("/", response_model=List[DocumentResponse])
async def list_documents(
    department: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all documents with optional filtering."""
    query = select(Document).where(Document.status != "deleted")
    if department:
        query = query.where(Document.department == department)
    if status:
        query = query.where(Document.status == status)
    query = query.order_by(Document.created_at.desc())

    result = await db.execute(query)
    documents = result.scalars().all()
    return [_doc_to_response(d) for d in documents]


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single document by ID."""
    result = await db.execute(
        select(Document).where(Document.id == uuid.UUID(doc_id))
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return _doc_to_response(document)


@router.delete("/{doc_id}")
async def delete_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a document and remove it from all indexes."""
    result = await db.execute(
        select(Document).where(Document.id == uuid.UUID(doc_id))
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Remove from indexes
    pipeline = get_indexing_pipeline()
    await pipeline.delete_document_from_indexes(document)

    # Invalidate cache
    cache = get_cache_service()
    await cache.invalidate_document(doc_id)

    # Delete file from disk
    storage = get_storage_service()
    storage.delete_file(document.file_path)

    # Soft delete in DB
    document.status = "deleted"
    await db.commit()

    return {"message": "Document deleted successfully", "id": doc_id}


@router.post("/{doc_id}/reindex")
async def reindex_document(
    doc_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Trigger re-indexing of an existing document."""
    result = await db.execute(
        select(Document).where(Document.id == uuid.UUID(doc_id))
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Remove old chunks from indexes first
    pipeline = get_indexing_pipeline()
    await pipeline.delete_document_from_indexes(document)

    # Delete old chunk records
    await db.execute(delete(Chunk).where(Chunk.document_id == uuid.UUID(doc_id)))
    await db.commit()

    background_tasks.add_task(_run_indexing, doc_id)
    return {"message": "Re-indexing started", "id": doc_id}


def _doc_to_response(doc: Document) -> DocumentResponse:
    return DocumentResponse(
        id=str(doc.id),
        name=doc.name,
        original_name=doc.original_name,
        department=doc.department,
        owner=doc.owner,
        tags=doc.tags or [],
        confidentiality=doc.confidentiality,
        version=doc.version,
        status=doc.status,
        chunk_count=doc.chunk_count or 0,
        file_size=doc.file_size,
        created_at=doc.created_at.isoformat() if doc.created_at else "",
        indexed_at=doc.indexed_at.isoformat() if doc.indexed_at else None,
    )
