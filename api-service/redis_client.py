import os

from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool


REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
REDIS_CHANNEL = "doc:results"


async def connect_to_redis() -> Redis:
    """
    Connect to Redis and return the client instance.
    """
    client = Redis.from_url(REDIS_URL, decode_responses=True)
    await client.ping()
    return client


async def connect_to_pubsub_redis() -> Redis:
    """
    Separate Redis connection for pub/sub with keepalive enabled.
    Pub/sub connections are long-lived and idle between messages,
    so a standard timeout will kill them prematurely.
    """
    pool = ConnectionPool.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_keepalive=True,
        socket_connect_timeout=5,
        socket_timeout=None,  # Disable socket timeout entirely for pub/sub
        health_check_interval=30,
    )
    client = Redis(connection_pool=pool)
    await client.ping()
    return client
