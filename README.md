# Event Driven Data Pipeline - Demo

An API with REST and WebSocket endpoints that trigger asynchronous workflows for:

* Document ingestion (read PDF and extract text while preserving header hierarchy)
* Document generation (write a short intro and summary of the PDF)

The workflows are managed by a workflow orchestrator service. The Temporal library is used to defined workflows and their activities. The workflow orchestrator assigns activities to workers.

There is currently 1 main workflow for document processing that fires parsing activities first, then generation activities. It is triggered by the /parse endpoint and can be tracked by calling the /workflow-status websocket for a given workflow ID (the workflow ID is returned byt he /parse endpoint).

## How to Run Locally

Use Docker:

```bash
bash scripts/up.sh
```

Go to:

* <http://localhost:8000/docs> for the REST API docs
* <http://localhost:8000/docs/ws> for the Websocket docs
* <http://localhost:8080> for the Temporal UI
* <http://localhost:8501> for the Streamlit parsing app

For websockets, there is a supplemental script to test the connections and see how a front-end would consume them:

```bash
python scripts/connect_to_websockets/connect.py
```

### Testing Services Independently

If you need to use Python to test anything independently, set up a virtual environment:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv --python 3.12
source .venv/bin/activate
touch requirements.txt
uv pip install -r requirements.txt
```
