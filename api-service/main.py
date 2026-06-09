import asyncio
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel
from temporalio.client import Client, WorkflowHandle

from shared.queues import WORKFLOW_TASK_QUEUE
from shared.temporal_client import connect_to_temporal
from shared.workflows import DocumentProcessingWorkflow

from connection_manager import manager
from redis_client import REDIS_CHANNEL, connect_to_redis


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class ParseRequest(BaseModel):
    document: str


class ParseResponse(BaseModel):
    workflow_id: str
    message: str


class HealthResponse(BaseModel):
    status: str


# =============================================================================
# GLOBALS
# =============================================================================

temporal_client: Client | None = None

ASYNCAPI_DOCS_PATH = Path(__file__).parent / "asyncapi-docs.yaml"
ASYNCAPI_UI_PATH = Path(__file__).parent / "asyncapi-docs.html"


# =============================================================================
# FASTAPI LIFESPAN
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    global temporal_client

    temporal_client = await connect_to_temporal()
    print("Connected to Temporal")

    redis = await connect_to_redis()
    asyncio.create_task(manager.start_subscriber(redis, REDIS_CHANNEL))
    print(f"Started Redis subscriber on channel: {REDIS_CHANNEL}")

    yield

    print("Shutting down API service")


# =============================================================================
# FASTAPI APP
# =============================================================================

app = FastAPI(
    title="Document Processing API",
    version="1.0.0",
    lifespan=lifespan,
)


# =============================================================================
# ROUTES
# =============================================================================

@app.get(
    "/health",
    response_model=HealthResponse,
)
async def health():

    return HealthResponse(
        status="ok",
    )


@app.get(
    "/ws-docs",
    response_class=FileResponse,
    summary="AsyncAPI YAML documentation",
    description="Returns the AsyncAPI YAML specification for the WebSocket API.",
    include_in_schema=False,  # Hide from Swagger UI
)
async def ws_docs_yaml():
    return FileResponse(
        path=ASYNCAPI_DOCS_PATH,
        media_type="application/yaml",
        filename="asyncapi-docs.yaml",
    )


@app.get("/docs/ws", response_class=FileResponse, include_in_schema=False)
async def ws_docs_ui():
    return FileResponse(path=ASYNCAPI_UI_PATH, media_type="text/html")


@app.post(
    "/parse",
    response_model=ParseResponse,
)
async def parse_document(request: ParseRequest):

    workflow_id = f"document-workflow-{uuid.uuid4()}"

    if temporal_client is None:
        raise RuntimeError("Temporal client not initialized")

    handle: WorkflowHandle = await temporal_client.start_workflow(
        DocumentProcessingWorkflow.__name__,
        args=[workflow_id, request.document],
        id=workflow_id,
        task_queue=WORKFLOW_TASK_QUEUE,
    )

    return ParseResponse(
        workflow_id=handle.id,
        message="Workflow started",
    )


@app.websocket("/generate")
async def generate_document(websocket: WebSocket):

    workflow_id = f"document-workflow-{uuid.uuid4()}"

    await manager.connect(workflow_id, websocket)

    try:
        await manager.send_status(workflow_id, "received", "Document received, generation started.")

        # TODO: replace the sleep and result below with a Temporal workflow.
        #
        #   handle = await temporal_client.start_workflow(
        #       DocumentProcessingWorkflow.__name__,
        #       id=workflow_id,
        #       task_queue=WORKFLOW_TASK_QUEUE,
        #   )
        #   result = await handle.result()

        await asyncio.sleep(20)
        result = {"status": "completed", "document": "placeholder"}

        await manager.send(workflow_id, result)

    except WebSocketDisconnect:
        print("Client disconnected before document generation completed")

    finally:
        await manager.disconnect(workflow_id, websocket)
