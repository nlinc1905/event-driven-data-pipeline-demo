# Event Driven Data Pipeline - Demo

Example of an event-driven data pipeline, where events are triggered by API requests. Events are processed asynchronously with Temporal. Workflows arrange different processing steps, based on what needs to be done, where each processing step is a micro-service with its own infrastructure.

## How to Run Locally

Use Docker:

```bash
bash scripts/up.sh
```

Go to <http://localhost:8000/docs> for the API and <http://localhost:8080> for the Temporal UI.

### Testing Services Independently

If you need to use Python to test anything independently, set up a virtual environment:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv --python 3.12
source .venv/bin/activate
touch requirements.txt
uv pip install -r requirements.txt
```
