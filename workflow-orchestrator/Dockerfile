FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY workflow-orchestrator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy submodule contents
COPY shared ./shared

# Copy worker code
COPY workflow-orchestrator/ .

CMD ["python", "main.py"]
