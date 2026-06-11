import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel
from temporalio.client import Client, WorkflowHandle

from shared.queues import WORKFLOW_TASK_QUEUE
from shared.temporal_client import connect_to_temporal
from shared.workflows import DocumentGenerationWorkflow, DocumentProcessingWorkflow

from connection_manager import manager
from redis_client import REDIS_CHANNEL, connect_to_redis, connect_to_pubsub_redis


logger = logging.getLogger(__name__)

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
    # task = asyncio.create_task(manager.start_subscriber(redis, REDIS_CHANNEL))
    pubsub_redis = await connect_to_pubsub_redis()
    task = asyncio.create_task(manager.start_subscriber(pubsub_redis, REDIS_CHANNEL))
    task.add_done_callback(
        lambda t: logger.error(f"Subscriber task exited: {t.exception()}") if not t.cancelled() and t.exception() else None
    )
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
    """
    WebSocket endpoint to receive document generation requests and send status updates.
    The client should send a JSON message with the following format:
    {
        "document": "The document content to be processed"
    }

    The server will respond with status updates and the final generated document through the WebSocket connection.
    """
    # Generate a unique workflow ID for the workflow to be processed in this WebSocket connection
    workflow_id = f"document-workflow-{uuid.uuid4()}"

    # Connect the WebSocket to the connection manager with the workflow ID
    await manager.connect(workflow_id, websocket)

    try:
        await manager.send_status(
            workflow_id, 
            "received", 
            f"Document received, generation started with workflow ID {workflow_id}."
        )

        # Start the Temporal workflow to process the document
        await temporal_client.start_workflow(
            DocumentGenerationWorkflow.__name__,
            args=[workflow_id, "document-placeholder"],
            id=workflow_id,
            task_queue=WORKFLOW_TASK_QUEUE,
        )

        # Hold the connection open until the client disconnects.
        # All further messages arrive via Redis pub/sub through the connection manager, including the result, 
        # so we do not need to await the workflow result here.
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        print(f"[{workflow_id}] Client disconnected")

    finally:
        await manager.disconnect(workflow_id, websocket)
