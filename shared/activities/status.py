import json
from typing import Optional

from redis.asyncio import Redis
from temporalio import activity

from shared.clients.redis_client import REDIS_CHANNEL, REDIS_URL


@activity.defn
async def publish_status(workflow_id: str, status: str, message: str, result: Optional[dict] = None) -> None:
    """
    Activity to publish status updates to Redis.
    The API service subscribes to these updates via the Redis channel, 
    to receive real-time status information from temporal workflows.

    :param workflow_id: The ID of the workflow sending the status update.
    :param status: The status of the workflow.
    :param message: The status message to be published.
    :param result: Optional result data to be included in the status update.
    """
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        payload = {
            "workflow_id": workflow_id,
            "result": {
                "type": "status",
                "status": status,
                "message": message,
                **({"result": result} if result is not None else {}),
            }
        }
        serialized = json.dumps(payload)
        await redis.publish(REDIS_CHANNEL, serialized)

        # Cache the terminal result so late-connecting clients can retrieve it
        if status in ("complete", "error"):
            await redis.set(f"result:{workflow_id}", serialized, ex=3600)  # expire after 1 hour
    finally:
        await redis.aclose()
