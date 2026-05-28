import asyncio
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel
from temporalio.client import Client, WorkflowHandle

# =============================================================================
# SHARED WORKFLOW IMPORTS
# =============================================================================
#
# In production:
# -----------------------------------------
# These would come from a shared package:
#
#     shared-temporal/workflows/
#
# For now we define a stub signature only.
#
# =============================================================================

class DocumentProcessingWorkflow:
    @staticmethod
    async def run(document: str) -> str:
        return ""


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


# =============================================================================
# FASTAPI LIFESPAN
# =============================================================================




async def connect_to_temporal() -> Client:
    """
    Helper function to connect to Temporal with retries, ensuring it is 
    up and ready before starting the worker.
    """

    temporal_host = os.getenv("TEMPORAL_HOST", "localhost:7233")

    while True:
        try:
            print(f"Connecting to Temporal at {temporal_host}")

            client = await Client.connect(
                temporal_host,
                namespace="default",
            )

            print("Connected to Temporal")

            return client

        except Exception as e:
            print(f"Temporal not ready yet: {e}")

            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):

    global temporal_client

    temporal_client = await connect_to_temporal()

    print("Connected to Temporal")

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


@app.post(
    "/parse",
    response_model=ParseResponse,
)
async def parse_document(request: ParseRequest):

    workflow_id = f"document-workflow-{uuid.uuid4()}"

    # -------------------------------------------------------------------------
    # Start workflow asynchronously
    # -------------------------------------------------------------------------

    if temporal_client is None:
        raise RuntimeError("Temporal client not initialized")

    handle: WorkflowHandle = await temporal_client.start_workflow(
        "DocumentProcessingWorkflow",
        request.document,
        id=workflow_id,
        task_queue="workflow-task-queue",
    )

    return ParseResponse(
        workflow_id=handle.id,
        message="Workflow started",
    )
