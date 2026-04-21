# Validator (and optional CPU-only tooling): slim image with bittensor only.
# **Miner** compose uses `docker/subnet-miner/Dockerfile` (CUDA + OpenFly VLM deps).
FROM python:3.11-slim

# OpenCV / unrealcv load libxcb at import time in ue_synthetic (headless still needs X client libs).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgomp1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libx11-6 \
    libxcb1 \
    libxcb-shm0 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt setup.py README.md ./
COPY template ./template
COPY neurons ./neurons
COPY scripts ./scripts

RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -e . \
    && pip install --no-cache-dir unrealcv opencv-python-headless

ENV PYTHONUNBUFFERED=1

CMD ["python", "neurons/validator.py", "--help"]
