from typing import AsyncGenerator, Optional

import httpx
import structlog
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

from config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


class LLMService:
    """
    Service for interacting with the local Ollama LLM via LangChain's
    ChatOllama wrapper. Falls back to raw HTTP only for model
    availability checks and pulling (LangChain has no API for these).
    """

    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.model = settings.llm_model
        self._chat: Optional[ChatOllama] = None

    def get_chat_model(self) -> ChatOllama:
        """Lazily build the LangChain ChatOllama client."""
        if self._chat is None:
            self._chat = ChatOllama(
                base_url=self.base_url,
                model=self.model,
                temperature=settings.llm_temperature,
                num_predict=settings.llm_max_tokens,
                num_ctx=settings.llm_context_window,
            )
        return self._chat

    # ── Model lifecycle (raw HTTP — not covered by LangChain) ──────────────────

    async def is_model_available(self) -> bool:
        """Check if the model is pulled and available in Ollama."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                if resp.status_code == 200:
                    models = resp.json().get("models", [])
                    return any(m["name"].startswith(self.model.split(":")[0]) for m in models)
        except Exception:
            pass
        return False

    async def pull_model(self) -> bool:
        """Pull the model into Ollama if not already present."""
        logger.info("Pulling LLM model", model=self.model)
        try:
            async with httpx.AsyncClient(timeout=600) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/pull",
                    json={"name": self.model},
                ) as resp:
                    async for line in resp.aiter_lines():
                        if line:
                            logger.debug("Pull progress", line=line[:100])
            logger.info("Model pulled successfully", model=self.model)
            return True
        except Exception as e:
            logger.error("Failed to pull model", error=str(e))
            return False

    # ── Generation (via LangChain) ──────────────────────────────────────────────

    async def generate(self, prompt: str, system: str = "") -> str:
        """Generate a response from the LLM using LangChain's ChatOllama."""
        chat = self.get_chat_model()
        messages = []
        if system:
            messages.append(SystemMessage(content=system))
        messages.append(HumanMessage(content=prompt))

        try:
            response = await chat.ainvoke(messages)
            return response.content
        except Exception as e:
            logger.error("LLM generation failed", error=str(e))
            raise

    async def generate_stream(self, prompt: str, system: str = "") -> AsyncGenerator[str, None]:
        """Stream a response from the LLM using LangChain's ChatOllama."""
        chat = self.get_chat_model()
        messages = []
        if system:
            messages.append(SystemMessage(content=system))
        messages.append(HumanMessage(content=prompt))

        async for chunk in chat.astream(messages):
            if chunk.content:
                yield chunk.content


_llm_service = None


def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
