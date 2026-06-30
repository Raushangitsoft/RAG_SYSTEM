from .routes.documents import router as documents_router
from .routes.query import router as query_router
from .routes.health import router as health_router

__all__ = ["documents_router", "query_router", "health_router"]
