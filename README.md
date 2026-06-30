# Hybrid RAG — Internal Document Intelligence Platform

Production-grade Hybrid RAG system. 100% local. No cloud LLM. No external APIs.

## Stack

| Layer | Technology |
|---|---|
| Frontend | Streamlit |
| Backend | FastAPI |
| Orchestration | LangGraph |
| Document Parser | Docling |
| Embedding | BAAI/bge-m3 (CPU) |
| Vector DB | Qdrant |
| Keyword Search | Elasticsearch (BM25) |
| Reranker | BAAI/bge-reranker-large |
| LLM | Qwen2.5 7B Instruct GGUF via Ollama |
| Cache | Redis |
| Metadata DB | PostgreSQL |
| Document Storage | Local Disk |
| Deployment | Docker Compose |

## Quick Start (EC2 Ubuntu)

### 1. Run setup script (first time only)
```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
# Log out and back in after this
```

### 2. Start the stack
```bash
chmod +x scripts/start.sh
./scripts/start.sh
```

### 3. Access
- **Streamlit Frontend:** http://your-ec2-ip:8501
- **FastAPI Docs:** http://your-ec2-ip:8000/docs
- **Health Check:** http://your-ec2-ip:8000/health

## EC2 Security Group Ports

Open these inbound ports in your EC2 Security Group:
- **8501** — Streamlit frontend
- **8000** — FastAPI backend (optional, for direct API access)

## Usage

1. Open the Streamlit UI at port 8501
2. Go to **Manage Documents** → upload your PDFs, DOCX, PPTX files
3. Wait for indexing to complete (status turns green)
4. Go to **Ask Documents** and start querying

## Folder Structure

```
hybrid-rag/
├── backend/
│   ├── api/routes/          # FastAPI endpoints
│   ├── services/            # Embedding, LLM, storage, cache
│   ├── retrieval/           # Qdrant, Elasticsearch, hybrid search
│   ├── reranker/            # BGE cross-encoder reranker
│   ├── ingestion/           # Document parser + indexing pipeline
│   ├── pipelines/           # LangGraph RAG orchestration
│   ├── prompts/             # Prompt templates
│   ├── models/              # SQLAlchemy DB models
│   ├── config/              # Settings
│   └── main.py
├── frontend/
│   └── app.py               # Streamlit UI
├── docker/postgres/
│   └── init.sql             # DB schema
├── data/
│   ├── documents/           # Raw uploaded files (local disk)
│   └── models/              # Downloaded ML models
├── scripts/
│   ├── setup.sh             # EC2 first-time setup
│   ├── start.sh             # Start stack
│   ├── stop.sh              # Stop stack
│   └── backup.sh            # Backup DB + files
├── docker-compose.yml
├── .env
└── .env.example
```

## Notes

- **First startup** downloads Qwen2.5 7B (~4GB) and BAAI models — takes 10–20 mins
- **16GB RAM** is the minimum. Keep other processes minimal.
- Models are cached in `data/models/` and Docker volumes — not re-downloaded on restart
- Documents stored in `data/documents/` on local disk (not MinIO)
- Run `./scripts/backup.sh` daily via cron for safety
