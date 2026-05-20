from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from database import init_db, SessionLocal, Computer
import datetime
import asyncio
import json
import logging

logging.basicConfig(
    filename="backend.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

app = FastAPI()

@app.on_event("startup")
async def startup():
    init_db()
    asyncio.create_task(check_offline())

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/computers")
def get_computers():
    db = SessionLocal()
    computers = db.query(Computer).all()
    result = [{"id": c.id, "name": c.name, "status": c.status, "last_seen": str(c.last_seen)} for c in computers]
    db.close()
    return result

@app.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket):
    await websocket.accept()
    computer_id = None
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            computer_id = msg.get("computer_id")
            event = msg.get("event")

            if event == "heartbeat" and computer_id:
                db = SessionLocal()
                computer = db.query(Computer).filter(Computer.id == computer_id).first()
                if computer:
                    computer.status = "online"
                    computer.last_seen = datetime.datetime.utcnow()
                    db.commit()
                    logging.info(f"Heartbeat от ПК {computer_id}")
                db.close()

            await websocket.send_text(json.dumps({"status": "ok"}))

    except WebSocketDisconnect:
        if computer_id:
            db = SessionLocal()
            computer = db.query(Computer).filter(Computer.id == computer_id).first()
            if computer:
                computer.status = "offline"
                db.commit()
            db.close()

async def check_offline():
    while True:
        await asyncio.sleep(15)
        db = SessionLocal()
        computers = db.query(Computer).filter(Computer.status == "online").all()
        now = datetime.datetime.utcnow()
        for computer in computers:
            if computer.last_seen and (now - computer.last_seen).seconds > 15:
                computer.status = "offline"
                logging.info(f"ПК {computer.id} помечен offline (нет heartbeat)")
        db.commit()
        db.close()
