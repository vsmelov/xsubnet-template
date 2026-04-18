# ffmpeg в образе — основная раскадровка; opencv-python-headless из requirements — запасной путь.
FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PYTHONUNBUFFERED=1

# Ключ и опции — через env / docker run -e / compose env_file
CMD ["python", "-m", "app.main"]
