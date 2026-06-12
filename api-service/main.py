import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from temporalio.client import Client, WorkflowHandle

from shared.queues import WORKFLOW_TASK_QUEUE
from shared.clients.redis_client import REDIS_CHANNEL, connect_to_redis, connect_to_pubsub_redis
from shared.clients.temporal_client import connect_to_temporal
from shared.workflows import DocumentProcessingWorkflow

from connection_manager import manager


# =============================================================================
# GLOBALS
# =============================================================================

logger = logging.getLogger(__name__)
temporal_client: Client | None = None

ASYNCAPI_DOCS_PATH = Path(__file__).parent / "asyncapi-docs.yaml"
ASYNCAPI_UI_PATH = Path(__file__).parent / "asyncapi-docs.html"


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class ParseRequest(BaseModel):
    """Model for a document parsing request."""
    document: str = Field(..., description="The document content to be processed.")


class ParseResponse(BaseModel):
    """Model for a document parsing response."""
    workflow_id: str = Field(..., description="The ID of the workflow.")
    message: str = Field(default="Workflow started.", description="A message indicating the status of the workflow.")


class HealthResponse(BaseModel):
    """Model for a health check response."""
    status: str = Field(..., description="The health status of the API service.")


# =============================================================================
# FASTAPI LIFESPAN
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan function to manage startup and shutdown of the API service, 
    including connections to Temporal and Redis. 
    """
    # Connect to Temporal
    global temporal_client
    temporal_client = await connect_to_temporal()
    logger.debug("Connected to Temporal")

    # Start a Redis client to create connections from a pool for immediate request/response actions
    redis_client = await connect_to_redis()
    # task = asyncio.create_task(manager.start_subscriber(redis_client, REDIS_CHANNEL))

    # Start a Redis client to create one long-lived pub/sub Redis connection for listening to workflow updates 
    # and sending them to WebSocket clients.
    pubsub_redis = await connect_to_pubsub_redis()
    task = asyncio.create_task(manager.start_subscriber(pubsub_redis, REDIS_CHANNEL))
    task.add_done_callback(
        lambda t: logger.error(f"Subscriber task exited: {t.exception()}") if not t.cancelled() and t.exception() else None
    )
    logger.debug(f"Started Redis subscriber on channel: {REDIS_CHANNEL}")

    yield

    logger.info("Shutting down API service")


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
    """
    Health check endpoint to verify that the API service is running.
    """
    return HealthResponse(status="ok")


@app.get(
    "/ws-docs",
    response_class=FileResponse,
    include_in_schema=False,
)
async def ws_docs_yaml():
    """
    Endpoint to serve the AsyncAPI YAML documentation for the WebSocket API.
    This is used by the AsyncAPI UI to load the API specification.
    """
    return FileResponse(
        path=ASYNCAPI_DOCS_PATH,
        media_type="application/yaml",
        filename="asyncapi-docs.yaml",
    )


@app.get("/docs/ws", response_class=FileResponse, include_in_schema=False)
async def ws_docs_ui():
    """
    Endpoint to serve the AsyncAPI UI for the WebSocket API documentation.
    """
    return FileResponse(path=ASYNCAPI_UI_PATH, media_type="text/html")


@app.post(
    "/parse",
    response_model=ParseResponse,
)
async def parse_document(request: ParseRequest):
    """
    REST endpoint to receive a document parsing request and start a Temporal workflow to process it. 
    This does not return the result of the workflow. Instead, it returns the workflow ID, 
    which can be used to poll for results or correlate with Redis pub/sub messages that are 
    emitted by the workflow. The workflow will publish the final result to Redis when complete.
    """
    # Generate a unique ID for the workflow, to be used by Temporal
    workflow_id = f"document-workflow-{uuid.uuid4()}"

    # Check the temporal client that should have been initialized in lifespan before trying to start a workflow
    if temporal_client is None:
        raise RuntimeError("Temporal client not initialized")

    # Start the Temporal workflow to process the document.
    # The workflow runs asynchronously and publishes status updates and the final result to Redis.
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
    # Generate a unique ID for the workflow, to be used by both Temporal and Redis pub/sub 
    # to correlate messages with the correct WebSocket connection.
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
            DocumentProcessingWorkflow.__name__,
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
