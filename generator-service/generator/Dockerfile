FROM python:3.12-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir openai-agents jinja2

# Copy prompt templates after dependencies so prompt changes do not invalidate the pip cache layer
COPY prompt_templates/ ./prompt_templates/
COPY generate.py .

ENV OPENAI_API_KEY=""

CMD ["python", "generate.py"]
