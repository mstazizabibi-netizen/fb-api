FROM python:3.10-slim

# FFmpeg সহ প্রয়োজনীয় ডিপেনডেন্সি ইনস্টল
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Worker কমানো হয়েছে যেন RAM ফুল হয়ে Crash না করে
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
