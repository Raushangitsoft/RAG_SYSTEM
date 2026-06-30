import time
from typing import TypedDict, List, Dict, Any, Optional

import structlog
import tiktoken
from langgraph.graph import StateGraph, END

from retrieval.hybrid_search import get_hybrid_search
from reranker.reranker_service import get_reranker_service
from services.llm_service import get_llm_service
from services.cache_service import get_cache_service
from prompts.templates import SYSTEM_PROMPT, QUERY_REWRITE_PROMPT
from config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

MAX_CONTEXT_TOKENS = int(settings.llm_context_window * 0.75)


def count_tokens(text: str) -> int:
    try:
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


# ── LangGraph State ────────────────────────────────────────────────────────────

class RAGState(TypedDict):
    query: str
    rewritten_query: str
    department: Optional[str]
    candidates: List[Dict[str, Any]]
    reranked: List[Dict[str, Any]]
    context: str
    sources: List[Dict[str, Any]]
    answer: str
    error: Optional[str]
    latency_ms: int
    from_cache: bool


# ── Pipeline Nodes ─────────────────────────────────────────────────────────────

async def rewrite_query(state: RAGState) -> RAGState:
    """Rewrite short/ambiguous queries into full natural language questions."""
    query = state["query"]

    # Skip rewriting if query is already detailed enough
    if len(query.split()) >= 8:
        state["rewritten_query"] = query
        return state

    try:
        llm = get_llm_service()
        prompt = QUERY_REWRITE_PROMPT.format(query=query)
        rewritten = await llm.generate(prompt)
        rewritten = rewritten.strip().strip('"').strip("'")
        # Fallback to original if rewrite is too long or weird
        if len(rewritten) > 300 or len(rewritten) < 5:
            rewritten = query
        state["rewritten_query"] = rewritten
        logger.info("Query rewritten", original=query, rewritten=rewritten)
    except Exception as e:
        logger.warning("Query rewrite failed, using original", error=str(e))
        state["rewritten_query"] = query

    return state


async def hybrid_search(state: RAGState) -> RAGState:
    """Run hybrid search (BM25 + vector) with RRF fusion."""
    search_service = get_hybrid_search()
    try:
        candidates = await search_service.search(
            query=state["rewritten_query"],
            top_k=settings.hybrid_search_top_k,
            department=state.get("department"),
        )
        state["candidates"] = candidates
        logger.info("Hybrid search complete", candidates=len(candidates))
    except Exception as e:
        logger.error("Hybrid search failed", error=str(e))
        state["candidates"] = []
        state["error"] = f"Search failed: {str(e)}"
    return state


async def rerank(state: RAGState) -> RAGState:
    """Rerank candidates with BGE cross-encoder."""
    if not state["candidates"]:
        state["reranked"] = []
        return state

    try:
        reranker = get_reranker_service()
        reranked = await reranker.rerank(
            query=state["rewritten_query"],
            candidates=state["candidates"],
            top_k=settings.reranker_top_k,
        )
        state["reranked"] = reranked
        logger.info("Reranking complete", top_k=len(reranked))
    except Exception as e:
        logger.warning("Reranking failed, using raw results", error=str(e))
        state["reranked"] = state["candidates"][:settings.reranker_top_k]
    return state


async def build_context(state: RAGState) -> RAGState:
    """Build context string from reranked chunks within token budget."""
    chunks = state["reranked"]
    if not chunks:
        state["context"] = ""
        state["sources"] = []
        return state

    context_parts = []
    sources = []
    total_tokens = count_tokens(SYSTEM_PROMPT) + count_tokens(state["query"]) + 200

    seen_content = set()

    for chunk in chunks:
        content = chunk["content"].strip()

        # Deduplicate
        content_hash = hash(content[:100])
        if content_hash in seen_content:
            continue
        seen_content.add(content_hash)

        chunk_tokens = count_tokens(content)
        if total_tokens + chunk_tokens > MAX_CONTEXT_TOKENS:
            break

        context_parts.append(
            f"[Source: {chunk['document_name']}, Page {chunk['page_number']}]\n{content}"
        )
        sources.append({
            "document_name": chunk["document_name"],
            "document_id": chunk.get("document_id", ""),
            "page_number": chunk["page_number"],
            "section_heading": chunk.get("section_heading", ""),
            "score": chunk.get("reranker_score", chunk.get("rrf_score", 0)),
        })
        total_tokens += chunk_tokens

    state["context"] = "\n\n---\n\n".join(context_parts)
    state["sources"] = sources
    logger.info("Context built", chunks_used=len(context_parts), tokens=total_tokens)
    return state


async def generate_answer(state: RAGState) -> RAGState:
    """Generate answer from local LLM using built context."""
    if not state["context"]:
        state["answer"] = "I couldn't find relevant information in the company documents for your query."
        return state

    llm = get_llm_service()
    user_prompt = f"Context:\n{state['context']}\n\nQuestion: {state['query']}"

    try:
        answer = await llm.generate(prompt=user_prompt, system=SYSTEM_PROMPT)
        state["answer"] = answer
    except Exception as e:
        logger.error("LLM generation failed", error=str(e))
        state["answer"] = "I encountered an error generating a response. Please try again."
        state["error"] = str(e)

    return state


# ── Build LangGraph ────────────────────────────────────────────────────────────

def build_rag_graph():
    graph = StateGraph(RAGState)

    graph.add_node("rewrite_query", rewrite_query)
    graph.add_node("hybrid_search", hybrid_search)
    graph.add_node("rerank", rerank)
    graph.add_node("build_context", build_context)
    graph.add_node("generate_answer", generate_answer)

    graph.set_entry_point("rewrite_query")
    graph.add_edge("rewrite_query", "hybrid_search")
    graph.add_edge("hybrid_search", "rerank")
    graph.add_edge("rerank", "build_context")
    graph.add_edge("build_context", "generate_answer")
    graph.add_edge("generate_answer", END)

    return graph.compile()


_rag_graph = None


def get_rag_graph():
    global _rag_graph
    if _rag_graph is None:
        _rag_graph = build_rag_graph()
    return _rag_graph


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_rag_pipeline(
    query: str,
    department: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the full RAG pipeline and return structured result."""
    start = time.time()
    cache = get_cache_service()

    # Cache lookup
    cache_key = f"{query}:{department or 'all'}"
    cached = await cache.get_query_result(cache_key)
    if cached:
        cached["from_cache"] = True
        return cached

    graph = get_rag_graph()
    initial_state: RAGState = {
        "query": query,
        "rewritten_query": query,
        "department": department,
        "candidates": [],
        "reranked": [],
        "context": "",
        "sources": [],
        "answer": "",
        "error": None,
        "latency_ms": 0,
        "from_cache": False,
    }

    final_state = await graph.ainvoke(initial_state)
    latency_ms = int((time.time() - start) * 1000)
    final_state["latency_ms"] = latency_ms

    result = {
        "query": final_state["query"],
        "rewritten_query": final_state["rewritten_query"],
        "answer": final_state["answer"],
        "sources": final_state["sources"],
        "latency_ms": latency_ms,
        "chunk_count": len(final_state["reranked"]),
        "from_cache": False,
        "error": final_state.get("error"),
    }

    # Cache successful results
    if not result["error"] and result["answer"]:
        await cache.set_query_result(cache_key, result)

    return result
