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


workflow_id = "document-workflow-debcb901-234f-44e7-bddb-c38264097915"
asyncio.run(listen(workflow_id, "workflow-status"))
