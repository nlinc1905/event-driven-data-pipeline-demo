FROM python:3.12-slim

WORKDIR /app

# Install dependencies
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
COPY parser-service/requirements-pytorch.txt .
RUN pip install --no-cache-dir -r requirements-pytorch.txt
COPY parser-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy submodule contents
COPY shared ./shared

# Copy worker code
COPY parser-service/ .

CMD ["python", "main.py"]
