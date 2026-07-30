FROM python:3.10-slim

# Install FFmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# main:app দিতে হবে (main.py:app নয়)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
