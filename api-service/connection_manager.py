import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket
from redis.asyncio import Redis


logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages active WebSocket connections for the document generation service.

    Connections are keyed by workflow_id, allowing targeted messaging when a
    Temporal workflow completes. A single workflow_id may have multiple
    connections (e.g. the same user on two tabs).
    """
    def __init__(self):
        # workflow_id -> list of active WebSocket connections on THIS instance
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, workflow_id: str, websocket: WebSocket) -> None:
        """
        Add a WebSocket connection to the manager.

        :param workflow_id: The ID of the workflow associated with the connection.
        :param websocket: The WebSocket connection to add.
        """
        await websocket.accept()
        self._connections.setdefault(workflow_id, []).append(websocket)
        logger.info(f"[{workflow_id}] Client connected ({self._count(workflow_id)} on this instance)")

    async def disconnect(self, workflow_id: str, websocket: WebSocket) -> None:
        """
        Remove a WebSocket connection from the manager. If no connections remain for workflow_id, remove the key.

        :param workflow_id: The ID of the workflow associated with the connection.
        :param websocket: The WebSocket connection to remove.
        """
        sockets = self._connections.get(workflow_id, [])
        if websocket in sockets:
            sockets.remove(websocket)
        if not sockets:
            self._connections.pop(workflow_id, None)
            logger.info(f"[{workflow_id}] No connections remaining on this instance")

    async def start_subscriber(self, redis: Redis, channel: str) -> None:
        """
        Run as a background task on startup. Listens for workflow completion
        events published by the generator service and forwards them to any
        local WebSocket connections for that workflow_id.

        :param redis: An instance of the Redis client to use for subscribing.
        :param channel: The Redis channel to subscribe to for workflow completion events.
        """
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        logger.info(f"Subscribed to Redis channel: {channel}")

        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                payload = json.loads(message["data"])
                workflow_id = payload["workflow_id"]
                if self.is_connected(workflow_id):
                    await self.send(workflow_id, payload["result"])
            except (KeyError, json.JSONDecodeError) as e:
                logger.warning(f"Malformed message on channel {channel}: {e}")

    async def send(self, workflow_id: str, message: dict[str, Any]) -> bool:
        """
        Send a message to all local connections for workflow_id.
        Returns True if at least one connection was reached.

        :param workflow_id: The ID of the workflow to send the message to.
        :param message: The message to send.

        :return: True if at least one connection was reached, False otherwise.
        """
        sockets = self._connections.get(workflow_id, [])
        if not sockets:
            return False

        results = await asyncio.gather(
            *[self._send_one(ws, message) for ws in sockets],
            return_exceptions=True,
        )
        return any(r is True for r in results)

    async def _send_one(self, websocket: WebSocket, message: dict[str, Any]) -> bool:
        """
        Send a message to a single WebSocket connection. Returns True if successful, False if an error occurs.

        :param websocket: The WebSocket connection to send the message to.
        :param message: The message to send.

        :return: True if the message was sent successfully, False if an error occurred."""
        try:
            await websocket.send_json(message)
            return True
        except Exception as e:
            logger.warning(f"Failed to send to websocket: {e}")
            return False

    def is_connected(self, workflow_id: str) -> bool:
        """
        Returns True if there is at least one active connection for workflow_id on this instance. 
        This function helps determine whether the connection manager running on this instance 
        should attempt to send a message for a given workflow_id. If False, the manager 
        skips sending.

        :param workflow_id: The ID of the workflow to check for active connections.
        """
        return bool(self._connections.get(workflow_id))

    def _count(self, workflow_id: str) -> int:
        """
        Returns the number of active connections for workflow_id on this instance.
        This function is used for logging purposes to track how many clients are connected for a given workflow_id.

        :param workflow_id: The ID of the workflow to count connections for.
        """
        return len(self._connections.get(workflow_id, []))


# Single shared instance imported by the route module
manager = ConnectionManager()
