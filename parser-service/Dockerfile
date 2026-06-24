FROM python:3.12-slim

# Streamlit bombs without setting the Python path
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

# Install shared package and its dependencies
COPY shared ./shared
RUN pip install ./shared

# Install system dependencies
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

# Install CPU-only PyTorch, OpenCV headless, and Docling
COPY parser-service/requirements-pytorch.txt .
RUN pip install --no-cache-dir -r requirements-pytorch.txt
COPY parser-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy worker code
COPY parser-service/ .

CMD ["python", "main.py"]
