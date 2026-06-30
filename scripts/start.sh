#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# Start Hybrid RAG Stack
# ──────────────────────────────────────────────────────────────────────────────
set -e

echo "==> Starting Hybrid RAG..."

# Create data dirs if not exists
mkdir -p data/documents data/models/embeddings data/models/reranker

# Copy env if not exists
if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚠️  Created .env from .env.example. Please review settings."
fi

# Build and start
docker-compose up --build -d

echo ""
echo "==> Waiting for services to be healthy..."
sleep 15

# Pull Ollama model (runs inside the ollama container)
echo "==> Pulling LLM model (this may take a while on first run)..."
docker exec rag_ollama ollama pull qwen2.5:7b-instruct-q4_K_M || \
    echo "⚠️ Model pull will happen automatically on first query."

echo ""
echo "✅ Hybrid RAG is running!"
echo ""
echo "  Frontend (Streamlit):  http://localhost:8501"
echo "  Backend API:           http://localhost:8000"
echo "  API Docs:              http://localhost:8000/docs"
echo "  Health Check:          http://localhost:8000/health"
echo ""
echo "  View logs:  docker-compose logs -f"
echo "  Stop:       docker-compose down"
