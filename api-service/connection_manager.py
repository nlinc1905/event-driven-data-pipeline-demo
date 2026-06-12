import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket
from redis.asyncio import Redis


logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages active WebSocket connections. Connections are stored in-memory on each instance 
    of the API service and keyed by workflow_id. When a temporal workflow completes, 
    it publishes a message to Redis with the workflow_id, which is then picked up by the subscriber 
    running on each instance. The subscriber checks if there are any active connections for that workflow_id 
    on that instance, and if so, forwards the message to those connections. This allows for targeted messaging 
    to the correct WebSocket clients when a workflow completes, without needing to maintain a centralized registry 
    of connections.

    A single workflow_id may have multiple connections (e.g. the same user on two tabs). 
    TODO: figure out what happens if a workflow has multiple connections
    """
    def __init__(self):
        # Store an in-memory mapping of workflow_id to a list of active WebSocket connections for that workflow,
        # on this instance.
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, workflow_id: str, websocket: WebSocket) -> None:
        """
        Add a WebSocket connection to the manager.

        :param workflow_id: The ID of the workflow associated with the connection.
        :param websocket: The WebSocket connection to add.
        """
        await websocket.accept()
        self._connections.setdefault(workflow_id, []).append(websocket)
        logger.info(
            f"Client connected for workflow ID: [{workflow_id}], "
            f"with {self._count(workflow_id)} websocket connections on this instance."
        )

    async def disconnect(self, workflow_id: str, websocket: WebSocket) -> None:
        """
        Remove a WebSocket connection from the manager. If no connections remain for workflow_id, remove the key
        from the self._connections dict.

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
        The API lifespan starts a background task that runs this subscriber function. 
        This function listens for messages on the specified Redis channel. 
        Messages should always contain workflow IDs. 
        When a message is received, this function checks if there are any local, active WebSocket connections 
        for the workflow_id on this instance. If there are, it forwards the message to those connections.

        :param redis: An instance of the Redis client to use for subscribing.
        :param channel: The Redis channel to subscribe to.
        """
        try:
            # Subscribe to the Redis channel via an infinitely long-lived connection.
            pubsub = redis.pubsub()
            await pubsub.subscribe(channel)
            logger.info(f"Subscribed to Redis channel: {channel}")

            # Listen for messages
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                # When a message is received, attempt to parse it and forward it to any active 
                # WebSocket connections for the workflow_id included in the message.
                try:
                    payload = json.loads(message["data"])
                    workflow_id = payload["workflow_id"]

                    logger.debug(f"Redis message received for workflow_id: {workflow_id}")
                    logger.debug(
                        f"Active websocket connections for the workflow on this instance: "
                        f"{list(self._connections.keys())}"
                    )

                    if self.is_connected(workflow_id):
                        # Send the message's result field
                        await self.send(workflow_id, payload["result"])
                    else:
                        logger.warning(f"No active connection found for workflow_id: {workflow_id}")
                except (KeyError, json.JSONDecodeError) as e:
                    logger.warning(f"Malformed message on channel {channel}: {e}")
        except Exception as e:
            logger.error(f"Redis subscriber crashed: {e}", exc_info=True)

    async def send(self, workflow_id: str, message: dict[str, Any]) -> bool:
        """
        Send a message to all local websocket connections for the workflow_id.
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

    async def send_status(self, workflow_id: str, status: str, message: str) -> bool:
        """
        Helper function to send a standardized status message to all connections for workflow_id.
        Returns True if at least one connection was reached. 
        Status messages facilitate communication between a temporal workflow and 
        websocket clients by providing a consistent format for conveying workflow status updates.

        :param workflow_id: The ID of the workflow to send the status message to.
        :param status: The status string (e.g. "processing", "completed", "failed").
        :param message: The message to include with the status.

        :return: True if at least one connection was reached, False otherwise.
        """
        return await self.send(workflow_id, {"type": "status", "status": status, "message": message})

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


# Single shared instance to be imported by the API root
manager = ConnectionManager()
