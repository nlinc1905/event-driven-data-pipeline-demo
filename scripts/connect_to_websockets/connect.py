import asyncio
import websockets
import json


async def generate():
    async with websockets.connect("ws://localhost:8000/generate") as ws:
        result = json.loads(await ws.recv())
        print("Document ready:", result)


asyncio.run(generate())
