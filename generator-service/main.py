import asyncio
import json
import os

from redis.asyncio import Redis
from temporalio import activity
from temporalio.worker import Worker

from shared.activities.generation import generate_document
from shared.queues import GENERATION_TASK_QUEUE
from shared.temporal_client import connect_to_temporal


REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
REDIS_CHANNEL = "doc:results"


# =============================================================================
# GENERATION ACTIVITY
# =============================================================================

@activity.defn(name=generate_document.__name__)
async def generate_document_implementation(workflow_id: str, document: str) -> str:
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

    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        await redis.publish(REDIS_CHANNEL, json.dumps({
            "workflow_id": workflow_id,
            "result": {"status": "completed", "document": generated},
        }))
        print(f"[Generator] Published result for workflow: {workflow_id}")
    finally:
        await redis.aclose()

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
