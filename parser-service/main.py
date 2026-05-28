import asyncio
import os

from temporalio.worker import Worker
from temporalio import activity

from shared.activities.parsing import parse_document
from shared.queues import PARSING_TASK_QUEUE
from shared.temporal_client import connect_to_temporal


# =============================================================================
# PARSING ACTIVITY
# =============================================================================

@activity.defn(name=parse_document.__name__)
async def parse_document_implementation(document: str) -> str:
    """
    Implementation of the parse_document activity. This is 
    where the document parsing logic goes. For example, there could be: 
    - OCR
    - parse a PDF
    - extract text
    - chunk content
    - store metadata
    """

    print(f"[Parser] Received document: {document}")

    await asyncio.sleep(20)

    parsed = document.upper()

    print(f"[Parser] Parsed result: {parsed}")

    return parsed


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
