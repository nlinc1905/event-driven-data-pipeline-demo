import os

from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool


REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
REDIS_CHANNEL = "doc:results"
REDIS_CHANNELS = [REDIS_CHANNEL]


async def connect_to_redis() -> Redis:
    """
    Connect to Redis and return the client instance from a connection pool. 

    The connection pool is managed internally by Redis.from_url and defaults to 
    unlimited max_connections so they are created on demand, 
    but a better default would match the application concurrency, 
    e.g. 8 workers * 4 threads = 32 max_connections.

    This connection is intended for immediate request/response actions and is not used for pub/sub.
    """
    client = Redis.from_url(REDIS_URL, decode_responses=True)
    # Test the connection with a ping to ensure Redis is available before proceeding
    await client.ping()
    return client


async def connect_to_pubsub_redis() -> Redis:
    """
    Connect to Redis for pub/sub with keepalive enabled.
    Pub/sub connections are long-lived and idle between messages,
    so a standard timeout will kill them prematurely. 

    The connection pool defined here creates one long-lived connection at application startup 
    (when it is called in lifespan) and held for the lifetime of the subscriber task, 
    which should live as long as the application is live. This connection is never returned to 
    the pool while listening. The connection is used for listening to workflow updates and 
    sending them to WebSocket clients. 

    The connection pool sends periodic TCP keepalive packets to prevent network devices 
    (e.g. load balancers) from closing idle connections, and 30 second health check 
    pings to ensure the connection is kept alive on the Redis server side.

    **IMPORTANT** This connection is intended for pub/sub operations and should be used exclusively for that purpose.
    """
    max_num_connections = 1 if isinstance(REDIS_CHANNELS, str) else len(REDIS_CHANNELS)
    pool = ConnectionPool.from_url(
        REDIS_URL,
        decode_responses=True,     # Return strings instead of bytes
        socket_keepalive=True,     # Enable TCP keepalive to prevent idle connections from being closed
        socket_connect_timeout=5,  # Short connect timeout to fail fast if Redis is unavailable
        socket_timeout=None,       # Disable socket timeout entirely for pub/sub
        health_check_interval=30,  # Enable health checks to keep the connection alive
        max_connections=max_num_connections,  # Limit to the number of subscription channels
    )
    client = Redis(connection_pool=pool)
    # Test the connection with a ping to ensure Redis is available before proceeding
    await client.ping()
    return client
