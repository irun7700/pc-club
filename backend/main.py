from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from database import init_db, SessionLocal, Computer, Session, Tariff
from pydantic import BaseModel
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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

class StartSession(BaseModel):
    computer_id: int
    tariff_id: int

class StopSession(BaseModel):
    session_id: int

@app.post("/sessions/start")
def start_session(data: StartSession):
    db = SessionLocal()
    computer = db.query(Computer).filter(Computer.id == data.computer_id).first()
    if not computer:
        db.close()
        raise HTTPException(status_code=404, detail="ПК не найден")
    active = db.query(Session).filter(
        Session.computer_id == data.computer_id,
        Session.ended_at == None
    ).first()
    if active:
        db.close()
        raise HTTPException(status_code=400, detail="На этом ПК уже идёт сессия")
    tariff = db.query(Tariff).filter(Tariff.id == data.tariff_id).first()
    if not tariff:
        db.close()
        raise HTTPException(status_code=404, detail="Тариф не найден")
    session = Session(
        computer_id=data.computer_id,
        tariff_id=data.tariff_id,
        started_at=datetime.datetime.utcnow()
    )
    db.add(session)
    db.commit()
    result = {"session_id": session.id, "started_at": str(session.started_at)}
    db.close()
    logging.info(f"Сессия {session.id} начата на ПК {data.computer_id}")
    return result

@app.post("/sessions/stop")
def stop_session(data: StopSession):
    db = SessionLocal()
    session = db.query(Session).filter(
        Session.id == data.session_id,
        Session.ended_at == None
    ).first()
    if not session:
        db.close()
        raise HTTPException(status_code=404, detail="Активная сессия не найдена")
    tariff = db.query(Tariff).filter(Tariff.id == session.tariff_id).first()
    now = datetime.datetime.utcnow()
    duration = (now - session.started_at).seconds / 3600
    total = round(duration * tariff.price_per_hour, 2)
    session.ended_at = now
    session.total_amount = total
    db.commit()
    result = {
        "session_id": session.id,
        "duration_minutes": round(duration * 60, 1),
        "total_amount": total
    }
    db.close()
    logging.info(f"Сессия {session.id} завершена, сумма: {total}")
    return result

@app.get("/sessions/active")
def get_active_sessions():
    db = SessionLocal()
    sessions = db.query(Session).filter(Session.ended_at == None).all()
    result = []
    for s in sessions:
        duration = (datetime.datetime.utcnow() - s.started_at).seconds / 60
        result.append({
            "session_id": s.id,
            "computer_id": s.computer_id,
            "tariff_id": s.tariff_id,
            "started_at": str(s.started_at),
            "duration_minutes": round(duration, 1)
        })
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
        db.commit()
        db.close()
