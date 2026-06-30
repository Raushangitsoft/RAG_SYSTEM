#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# Backup script for Hybrid RAG
# Backs up: PostgreSQL DB + raw document files
# Run via cron: 0 2 * * * /path/to/hybrid-rag/scripts/backup.sh
# ──────────────────────────────────────────────────────────────────────────────
set -e

BACKUP_DIR="${BACKUP_DIR:-/backup/hybrid-rag}"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

echo "==> Backing up PostgreSQL..."
docker exec rag_postgres pg_dump -U raguser ragdb | gzip > "$BACKUP_DIR/postgres_$DATE.sql.gz"

echo "==> Backing up documents..."
tar -czf "$BACKUP_DIR/documents_$DATE.tar.gz" -C /data documents/

# Keep last 7 days only
find "$BACKUP_DIR" -name "*.gz" -mtime +7 -delete

echo "✅ Backup complete: $BACKUP_DIR"
echo "   Files: $(ls $BACKUP_DIR | tail -5)"
