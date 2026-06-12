import json
import os

from redis.asyncio import Redis
from temporalio import activity


REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
REDIS_CHANNEL = "doc:results"


@activity.defn
async def publish_status(workflow_id: str, message: str) -> None:
    """
    Activity to publish status updates to Redis.
    The API service subscribes to these updates via the Redis channel, 
    to receive real-time status information from temporal workflows.

    :param workflow_id: The ID of the workflow sending the status update.
    :param message: The status message to be published.
    """
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        await redis.publish(REDIS_CHANNEL, json.dumps({
            "workflow_id": workflow_id,
            "result": {"type": "status", "status": "processing", "message": message},
        }))
    finally:
        await redis.aclose()
