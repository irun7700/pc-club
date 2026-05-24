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

import subprocess
import platform

def execute_command(command):
    system = platform.system()
    try:
        if command == "shutdown":
            if system == "Windows":
                subprocess.run(["shutdown", "/s", "/t", "5"], check=True)
            else:
                subprocess.run(["sudo", "shutdown", "-h", "now"], check=True)
            logging.info(f"Выполнена команда: {command}")
        elif command == "restart":
            if system == "Windows":
                subprocess.run(["shutdown", "/r", "/t", "5"], check=True)
            else:
                subprocess.run(["sudo", "shutdown", "-r", "now"], check=True)
            logging.info(f"Выполнена команда: {command}")
        elif command == "lock":
            if system == "Windows":
                subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=True)
            elif system == "Darwin":
                subprocess.run(["pmset", "displaysleepnow"], check=True)
            logging.info(f"Выполнена команда: {command}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Команда выполнена: {command}")
    except Exception as e:
        logging.error(f"Ошибка выполнения команды {command}: {e}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Ошибка команды {command}: {e}")

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
                async def heartbeat():
                    while True:
                        msg = {"computer_id": COMPUTER_ID, "event": "heartbeat"}
                        await ws.send(json.dumps(msg))
                        await asyncio.sleep(HEARTBEAT_INTERVAL)
                async def listen():
                    async for message in ws:
                        try:
                            data = json.loads(message)
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Получено: {data}")
                            if data.get("event") == "heartbeat_ack":
                                print(f"[{datetime.now().strftime('%H:%M:%S')}] Heartbeat ✓")
                            elif data.get("event") == "command":
                                cmd = data.get("command")
                                print(f"[{datetime.now().strftime('%H:%M:%S')}] Команда: {cmd}")
                                execute_command(cmd)
                        except Exception as e:
                            logging.error(f"Ошибка обработки сообщения: {e}")
                await asyncio.gather(heartbeat(), listen())

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Ошибка: {e}")
            logging.warning(f"Ошибка соединения: {e}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Переподключаюсь через {delay} сек...")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)

asyncio.run(connect())
