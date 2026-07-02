FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential libpq-dev libmagic1 \
    poppler-utils tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create document storage directories
RUN mkdir -p /app/data/documents /app/data/models

# Pre-trigger Docling's lazy model downloads (e.g. deepsearch_glm POS models)
# while still root, then open up permissions so the non-root runtime user
# (appuser) can read/write these resources without hitting Permission denied.
RUN python3 -c "from docling.document_converter import DocumentConverter; DocumentConverter()" || true
RUN chmod -R a+rwX /usr/local/lib/python3.11/site-packages/deepsearch_glm/ || true

# Non-root user for security
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-level", "info"]