from fastapi import APIRouter
from services.cache_service import get_cache_service
from retrieval.qdrant_service import get_qdrant_service
from retrieval.elasticsearch_service import get_es_service
from services.llm_service import get_llm_service

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    """Basic health check."""
    return {"status": "ok"}


@router.get("/health/detailed")
async def detailed_health():
    """Detailed health check for all services."""
    results = {}

    try:
        cache = get_cache_service()
        results["redis"] = await cache.health_check()
    except Exception:
        results["redis"] = False

    try:
        qdrant = get_qdrant_service()
        results["qdrant"] = await qdrant.health_check()
    except Exception:
        results["qdrant"] = False

    try:
        es = get_es_service()
        results["elasticsearch"] = await es.health_check()
    except Exception:
        results["elasticsearch"] = False

    try:
        llm = get_llm_service()
        results["ollama"] = await llm.is_model_available()
    except Exception:
        results["ollama"] = False

    all_ok = all(results.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "services": results,
    }
