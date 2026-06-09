import asyncio
import websockets
import json


async def generate():
    async with websockets.connect("ws://localhost:8000/generate") as ws:
        async for message in ws:
            data = json.loads(message)
            print("Received:", data)
            if data.get("status") in ("completed", "failed"):
                break


asyncio.run(generate())
