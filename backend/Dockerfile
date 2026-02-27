# Stock Investing Model - Backend (FastAPI)
FROM python:3.11-slim

WORKDIR /app

# libgomp1  — required by LightGBM (OpenMP runtime); stripped from slim images
# libgcc-s1 — required by hmmlearn / scipy on slim images
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        libgcc-s1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Railway sets PORT at runtime; fallback 8002 for local
EXPOSE 8002
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8002}"]
