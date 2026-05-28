import asyncio

from temporalio import activity
from temporalio.worker import Worker

from shared.activities.generation import generate_document
from shared.queues import GENERATION_TASK_QUEUE
from shared.temporal_client import connect_to_temporal

# =============================================================================
# GENERATION ACTIVITY
# =============================================================================

@activity.defn(name=generate_document.__name__)
async def generate_document_implementation(document: str) -> str:
    """
    Implementation of the generate_document activity. This is 
    where the document generation logic goes. For example, there could be: 
    - summarization
    - content generation
    """

    print(f"[Generator] Received document: {document}")

    await asyncio.sleep(20)

    generated = document.upper()[:2]

    print(f"[Generator] Generated result: {generated}")

    return generated


# =============================================================================
# WORKER
# =============================================================================

async def main():

    client = await connect_to_temporal()

    worker = Worker(
        client,
        task_queue=GENERATION_TASK_QUEUE,
        activities=[generate_document_implementation],
    )

    print("Generator worker started")
    print(f"Listening on task queue: {GENERATION_TASK_QUEUE}")

    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
