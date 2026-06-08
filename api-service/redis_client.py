import os

from redis.asyncio import Redis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
REDIS_CHANNEL = "doc:results"


async def connect_to_redis() -> Redis:
    """
    Connect to Redis and return the client instance.
    """
    client = Redis.from_url(REDIS_URL, decode_responses=True)
    await client.ping()
    return client
