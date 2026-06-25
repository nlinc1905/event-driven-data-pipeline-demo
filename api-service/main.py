import asyncio
import json
import logging
import shutil
import uuid
from base64 import b64encode
from contextlib import asynccontextmanager
from json import JSONDecodeError
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from temporalio.client import Client, WorkflowHandle

from shared.activities.parsing import ParseDocumentRequest
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

DOCUMENT_STORAGE_DIR = Path("/documents")
ASYNCAPI_DOCS_PATH = Path(__file__).parent / "asyncapi-docs.yaml"
ASYNCAPI_UI_PATH = Path(__file__).parent / "asyncapi-docs.html"


# =============================================================================
# Helper Functions
# =============================================================================

async def save_upload(document_id: str, file: UploadFile) -> str:
    """
    Save an uploaded file to a shared storage volume.

    :param document_id: The ID of the document.
    :param file: The uploaded file to save.

    :return: The path to the saved file on the mounted volume.
    """
    DOCUMENT_STORAGE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )
    pdf_path = DOCUMENT_STORAGE_DIR / f"{document_id}.pdf"

    with pdf_path.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    return str(pdf_path)


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class ParseResponse(BaseModel):
    """Model for a document parsing response."""
    workflow_id: str = Field(..., description="The ID of the workflow.")
    message: str = Field(default="Workflow started.", description="A message indicating the status of the workflow.")


class HealthResponse(BaseModel):
    """Model for a health check response."""
    status: str = Field(..., description="The health status of the API service.")


class PdfBase64Response(BaseModel):
    """Model for a PDF file response."""
    filename: str = Field(..., description="The name of the PDF file.")
    content_type: str = Field(..., description="The MIME type of the PDF file.")
    base64_data: str = Field(..., description="The base64-encoded content of the PDF file.")


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
    global redis_client
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


@app.post("/pdf/to-base64", response_model=PdfBase64Response)
async def pdf_to_base64(file: UploadFile = File(...)):
    """
    Endpoint to convert an uploaded PDF file to a base64-encoded string.
    This is useful for back-end development purposes
    (it replaces what the front-end would do; send the byte string directly to the workflow webhook endpoint). 
    The endpoint returns the base64-encoded string along with the filename and content type.
    """
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="File must be a PDF."
        )

    pdf_bytes = await file.read()

    return PdfBase64Response(
        filename=file.filename,
        content_type=file.content_type,
        base64_data=b64encode(pdf_bytes).decode("utf-8"),
    )


@app.post(
    "/parse",
    response_model=ParseResponse,
)
async def parse_document(
    document_id: str = Query(..., description="The ID of the document to be processed."),
    file: UploadFile = File(..., description="The (PDF file) document content to be processed."),
):
    """
    REST endpoint to receive a document parsing request and start a Temporal workflow to process it. 
    This does not return the result of the workflow. Instead, it returns the workflow ID, 
    which can be used to poll for results or correlate with Redis pub/sub messages that are 
    emitted by the workflow. The workflow will publish the final result to Redis when complete.
    """
    # Validate the uploaded file type
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="File must be a PDF",
        )

    # Check the temporal client that should have been initialized in lifespan before trying to start a workflow
    if temporal_client is None:
        raise RuntimeError("Temporal client not initialized")

    # Save the uploaded PDF file to the shared volume and get the path
    try:
        pdf_path = await save_upload(
            document_id=document_id, 
            file=file
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save uploaded PDF file: {str(e)}"
        )

    # Generate a unique ID for the workflow, to be used by Temporal
    workflow_id = f"document-workflow-{uuid.uuid4()}"

    # Start the Temporal workflow to process the document.
    # The workflow runs asynchronously and publishes status updates and the final result to Redis.
    formatted_request = ParseDocumentRequest(
        workflow_id=workflow_id,
        document_id=document_id, 
        pdf_path=pdf_path
    )
    handle: WorkflowHandle = await temporal_client.start_workflow(
        DocumentProcessingWorkflow.__name__,
        args=[workflow_id, formatted_request],
        id=workflow_id,
        task_queue=WORKFLOW_TASK_QUEUE,
    )

    return ParseResponse(
        workflow_id=handle.id,
        message="Workflow started",
    )


@app.websocket("/workflow-status")
async def workflow_status(websocket: WebSocket):
    """
    WebSocket endpoint to receive workflow status updates. 
    The client should send a JSON message with the following format:
    {
        "workflow_id": "The ID of the workflow to subscribe to"
    }

    The server will respond with status updates and the final result through the WebSocket connection.
    """
    workflow_id = None
    try:
        # Accept the WebSocket connection. This is required before sending any messages to the client.
        await websocket.accept() 

        # Wait for the initial message from the client containing the workflow ID
        initial_message = await websocket.receive_json()
        workflow_id = initial_message.get("workflow_id")
        if not workflow_id:
            await websocket.accept()   # must accept before we can send a close
            await websocket.send_json({"error": "No 'workflow_id' provided."})
            await websocket.close(code=1008)
            return

        # Check for a cached result BEFORE subscribing - this handles the race condition
        # where the workflow finished between POST /parse and WS connect.
        cached = await redis_client.get(f"result:{workflow_id}")
        if cached:
            await websocket.send_json(json.loads(cached))
            await websocket.close(code=1000)
            # Drain any remaining messages from the client so the
            # close handshake completes before the handler returns.
            try:
                while True:
                    await asyncio.wait_for(websocket.receive_text(), timeout=1)
            except (asyncio.TimeoutError, WebSocketDisconnect, RuntimeError):
                pass
            return

        # Register with the connection manager and send ack.
        await manager.connect(workflow_id, websocket)
        await manager.send_status(
            workflow_id,
            "received",
            f"Tracking workflow {workflow_id}",
        )

        # Hold the connection open. The manager will call websocket.close()
        # when it fans out a terminal status (complete/error) from Redis,
        # which causes receive_text() to raise WebSocketDisconnect.
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                # Send a ping to keep the connection alive if the client
                # hasn't sent anything (e.g. pure listener pattern).
                await websocket.send_json({"type": "ping"})

    except JSONDecodeError:
        if workflow_id is None:
            await websocket.accept()
        await websocket.send_json({"error": "Invalid JSON"})
        await websocket.close(code=1003)

    except WebSocketDisconnect:
        logger.info(f"[{workflow_id}] Client disconnected")

    finally:
        if workflow_id:
            await manager.disconnect(workflow_id, websocket)
