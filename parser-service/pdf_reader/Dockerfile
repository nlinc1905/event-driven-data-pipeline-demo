# Use this dockerfile to test run the extractor with a canned file

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# -------------------------------------------------
# System dependencies
# -------------------------------------------------
RUN apt-get update && apt-get install -y \
    build-essential \
    poppler-utils \
    tesseract-ocr \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libgl1 \
    git \
    && rm -rf /var/lib/apt/lists/*

# -------------------------------------------------
# Install CPU-only PyTorch, OpenCV headless, and Docling
# -------------------------------------------------
RUN pip install --no-cache-dir \
    torch \
    torchvision \
    torchaudio \
    --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir \
    opencv-python-headless \
    docling

COPY extractor.py .

CMD ["python", "extractor.py", "sample.pdf", "output/output.json"]
# CMD ["/bin/bash"]
