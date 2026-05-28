FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY api-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy submodule contents
COPY shared ./shared

# Copy worker code
COPY api-service/ .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
