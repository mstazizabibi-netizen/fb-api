FROM python:3.10-slim

# System Level Dependencies (FFmpeg & necessary tools)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements install
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Application code copy
COPY . .

# Dynamic PORT system for Railway (502 bad gateway আটকাবে)
CMD sh -c "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"
