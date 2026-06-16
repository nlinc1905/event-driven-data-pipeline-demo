FROM python:3.12-slim

WORKDIR /app

# Install shared package and its dependencies
COPY shared ./shared
RUN pip install ./shared

# Install dependencies
# COPY generator-service/requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt

# Copy worker code
COPY generator-service/ .

CMD ["python", "main.py"]
