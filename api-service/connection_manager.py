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

    # -------------------------------------------------------------------------
    # Connection lifecycle
    # -------------------------------------------------------------------------

    async def connect(self, workflow_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(workflow_id, []).append(websocket)
        logger.info(f"[{workflow_id}] Client connected ({self._count(workflow_id)} on this instance)")

    async def disconnect(self, workflow_id: str, websocket: WebSocket) -> None:
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

    # -------------------------------------------------------------------------
    # Sending
    # -------------------------------------------------------------------------

    async def send(self, workflow_id: str, message: dict[str, Any]) -> bool:
        """
        Send a message to all local connections for workflow_id.
        Returns True if at least one connection was reached.
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
        try:
            await websocket.send_json(message)
            return True
        except Exception as e:
            logger.warning(f"Failed to send to websocket: {e}")
            return False

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def is_connected(self, workflow_id: str) -> bool:
        return bool(self._connections.get(workflow_id))

    def _count(self, workflow_id: str) -> int:
        return len(self._connections.get(workflow_id, []))


# Single shared instance imported by the route module
manager = ConnectionManager()
