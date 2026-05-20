import asyncio
import websockets
import json

async def test():
    uri = "ws://localhost:8000/ws/agent"
    async with websockets.connect(uri) as ws:
        msg = {"computer_id": 1, "event": "heartbeat"}
        await ws.send(json.dumps(msg))
        response = await ws.recv()
        print("Heartbeat отправлен! Открывай браузер — у тебя 30 секунд")
        await asyncio.sleep(30)
        print("Готово")

asyncio.run(test())
