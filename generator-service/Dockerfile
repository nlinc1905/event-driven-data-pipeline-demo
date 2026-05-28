FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY generator-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy submodule contents
COPY shared ./shared

# Copy worker code
COPY generator-service/ .

CMD ["python", "main.py"]
