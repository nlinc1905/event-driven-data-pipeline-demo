import asyncio
import json

from shared.clients import redis_client
from temporalio import activity
from temporalio.worker import Worker

from shared.activities.parsing import parse_document, ParseDocumentRequest, ParseDocumentResponse
from shared.queues import PARSING_TASK_QUEUE
from shared.clients.redis_client import REDIS_CHANNEL, connect_to_redis, connect_to_pubsub_redis
from shared.clients.temporal_client import connect_to_temporal

from pdf_reader import extract_pdf


# =============================================================================
# PARSING ACTIVITY
# =============================================================================

@activity.defn(name=parse_document.__name__)
async def parse_document_implementation(request: ParseDocumentRequest) -> ParseDocumentResponse:
    """
    Implementation of the parse_document activity. This is 
    where the document parsing logic goes. For example, there could be: 
    - OCR
    - parse a PDF
    - extract text
    - chunk content
    - store metadata

    During the activity, status updates are published to Redis directly, 
    because this activity cannot call the Temporal activity publish_status.
    """
    # Start a Redis client to create connections from a pool for immediate request/response actions
    redis_client = await connect_to_redis()

    # Extract things from the request
    workflow_id = request.workflow_id
    doc_id = request.document_id
    pdf_path = request.pdf_path

    try:
        # Publish a status update to Redis indicating that the parsing has started
        await redis_client.publish(REDIS_CHANNEL, json.dumps({
            "workflow_id": workflow_id,
            "result": {"type": "status", "status": "processing", "message": "Parsing document..."},
        }))

        # Docling is CPU bound, so we run it in a separate thread to avoid blocking the event loop
        parsed: dict = await asyncio.to_thread(extract_pdf, pdf_path, None)

        # Publish a status update to Redis indicating that the parsing has completed
        await redis_client.publish(REDIS_CHANNEL, json.dumps({
            "workflow_id": workflow_id,
            "result": {"type": "status", "status": "processing", "message": "Parsing complete"},
        }))
    finally:
        await redis_client.aclose()

    return ParseDocumentResponse(
        workflow_id=workflow_id,
        document_id=doc_id,
        markdown=parsed.get("full_markdown", ""),
        metadata=parsed.get("metadata", {}),
    )


# =============================================================================
# WORKER
# =============================================================================


async def main():

    client = await connect_to_temporal()

    worker = Worker(
        client,
        task_queue=PARSING_TASK_QUEUE,
        activities=[parse_document_implementation],
    )

    print("Parser worker started")
    print(f"Listening on task queue: {PARSING_TASK_QUEUE}")

    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
