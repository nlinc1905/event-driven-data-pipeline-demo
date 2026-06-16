FROM python:3.12-slim

WORKDIR /app

# Install shared package and its dependencies
COPY shared ./shared
RUN pip install ./shared

# Install dependencies
# COPY workflow-orchestrator/requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt

# Copy worker code
COPY workflow-orchestrator/ .

CMD ["python", "main.py"]
