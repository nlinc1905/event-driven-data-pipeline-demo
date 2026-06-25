import asyncio
import json

from shared.clients import redis_client
from temporalio import activity
from temporalio.worker import Worker

from shared.activities.generation import generate_document
from shared.queues import GENERATION_TASK_QUEUE
from shared.clients.redis_client import REDIS_CHANNEL, connect_to_redis, connect_to_pubsub_redis
from shared.clients.temporal_client import connect_to_temporal


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

    During the activity, status updates are published to Redis directly, 
    because this activity cannot call the Temporal activity publish_status.
    """
    # Start a Redis client to create connections from a pool for immediate request/response actions
    redis_client = await connect_to_redis()

    try:
        # Publish a status update to Redis indicating that the generation has started
        await redis_client.publish(REDIS_CHANNEL, json.dumps({
            "workflow_id": workflow_id,
            "result": {"type": "status", "status": "processing", "message": "Generating document..."},
        }))

        # TODO: Implement the actual document generation logic here. For now, we simulate a delay and generate a simple result.
        await asyncio.sleep(20)
        generated = document.upper()[:2]

        # Publish a status update to Redis indicating that the generation has completed
        await redis_client.publish(REDIS_CHANNEL, json.dumps({
            "workflow_id": workflow_id,
            "result": {"type": "status", "status": "processing", "message": "Generation complete"},
        }))
    finally:
        await redis_client.aclose()

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
