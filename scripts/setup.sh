#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# Hybrid RAG — EC2 Ubuntu Setup Script
# Run this ONCE on a fresh Ubuntu EC2 instance
# ──────────────────────────────────────────────────────────────────────────────
set -e

echo "==> Updating system packages..."
sudo apt-get update -y
sudo apt-get upgrade -y

echo "==> Installing system dependencies..."
sudo apt-get install -y \
    curl wget git unzip \
    build-essential \
    ca-certificates \
    gnupg lsb-release \
    htop

echo "==> Installing Docker..."
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
rm get-docker.sh

echo "==> Installing Docker Compose..."
COMPOSE_VERSION="v2.29.1"
sudo curl -L "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" \
    -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

echo "==> Creating data directories..."
sudo mkdir -p /data/documents
sudo mkdir -p /data/models/embeddings
sudo mkdir -p /data/models/reranker
sudo chown -R $USER:$USER /data

echo "==> Docker version:"
docker --version
docker-compose --version

echo ""
echo "✅ Setup complete!"
echo ""
echo "IMPORTANT: Log out and back in for Docker group permissions to take effect."
echo "Then run: cd hybrid-rag && ./scripts/start.sh"
