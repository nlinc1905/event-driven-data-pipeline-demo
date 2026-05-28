import asyncio
import os

from temporalio.client import Client
from temporalio.worker import Worker
from temporalio import activity

from shared.activities.generation import generate_document


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


async def main():

    client = await connect_to_temporal()

    worker = Worker(
        client,
        task_queue="generation-task-queue",
        activities=[generate_document_implementation],
    )

    print("Generator worker started")
    print("Listening on task queue: generation-task-queue")

    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
