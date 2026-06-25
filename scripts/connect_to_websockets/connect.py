import asyncio
import websockets
import json


async def listen(workflow_id: str, websocket_endpoint: str):
    async with websockets.connect(f"ws://localhost:8000/{websocket_endpoint}") as ws:
        # Send the workflow ID to the WebSocket server to start listening for updates
        await ws.send(json.dumps({"workflow_id": workflow_id}))
        # Listen for messages from the WebSocket server
        print(f"Listening for updates on workflow ID: {workflow_id}")
        try:
            async for message in ws:
                data = json.loads(message)
                print("Received:", data)
                if data.get("status") in ("complete", "error"):
                    break
        except websockets.exceptions.ConnectionClosedOK:
            print("Server closed connection cleanly")


workflow_id = "document-workflow-f4c201db-811a-45aa-83a0-1b123ecdfd5a"
asyncio.run(listen(workflow_id, "workflow-status"))
