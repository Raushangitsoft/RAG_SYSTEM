import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from api.routes.documents import router as documents_router
from api.routes.query import router as query_router
from api.routes.health import router as health_router
from api.middleware.logging import logging_middleware
from models.database import engine, Base
from services.llm_service import get_llm_service
from config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logger.info("Starting Hybrid RAG Backend", env=settings.app_env)

    # Create DB tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready")

    # Ensure Ollama model is available
    llm = get_llm_service()
    if not await llm.is_model_available():
        logger.info("LLM model not found, pulling...", model=settings.llm_model)
        await llm.pull_model()
    else:
        logger.info("LLM model ready", model=settings.llm_model)

    # Ensure Qdrant collection exists
    from retrieval.qdrant_service import get_qdrant_service
    qdrant = get_qdrant_service()
    await qdrant.ensure_collection()
    logger.info("Qdrant collection ready")

    # Ensure ES index exists
    from retrieval.elasticsearch_service import get_es_service
    es = get_es_service()
    await es.ensure_index()
    logger.info("Elasticsearch index ready")

    logger.info("Hybrid RAG Backend started successfully")
    yield

    logger.info("Shutting down Hybrid RAG Backend")
    async with engine.begin() as conn:
        pass


app = FastAPI(
    title="Hybrid RAG API",
    description="Production-grade Hybrid RAG system for internal document intelligence",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Middleware
app.middleware("http")(logging_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health_router)
app.include_router(documents_router, prefix="/api/v1")
app.include_router(query_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "name": "Hybrid RAG API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }
