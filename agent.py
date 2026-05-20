import asyncio
import websockets
import json
import logging
from datetime import datetime

logging.basicConfig(
    filename="agent.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

COMPUTER_ID = 1
SERVER_URL = "ws://localhost:8000/ws/agent"
HEARTBEAT_INTERVAL = 5

async def connect():
    delay = 1
    while True:
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Подключаюсь к серверу...")
            logging.info("Подключаюсь к серверу...")
            async with websockets.connect(SERVER_URL) as ws:
                delay = 1
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Подключён! Отправляю heartbeat каждые {HEARTBEAT_INTERVAL} сек")
                logging.info("Подключён к серверу")
                while True:
                    msg = {"computer_id": COMPUTER_ID, "event": "heartbeat"}
                    await ws.send(json.dumps(msg))
                    response = await ws.recv()
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Heartbeat ✓")
                    logging.info("Heartbeat отправлен")
                    await asyncio.sleep(HEARTBEAT_INTERVAL)

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Ошибка: {e}")
            logging.warning(f"Ошибка соединения: {e}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Переподключаюсь через {delay} сек...")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)

asyncio.run(connect())
