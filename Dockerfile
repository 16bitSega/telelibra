# Librarian AI - Playwright-enabled Python 3.11 Container
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    OBSIDIAN_VAULT_PATH=/vault \
    DATABASE_PATH=/app/data/processed_links.db

WORKDIR /app

# Install system dependencies needed for Playwright and Trafilatura
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium browser and its OS dependencies
RUN playwright install --with-deps chromium

# Copy application source code
COPY . .

# Ensure data directory exists
RUN mkdir -p /app/data /vault

ENTRYPOINT ["python", "main.py"]
