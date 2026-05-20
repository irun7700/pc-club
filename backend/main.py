from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from database import init_db, SessionLocal, Computer, Session, Tariff, Client, Transaction
from pydantic import BaseModel
from typing import Optional
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

# --- Клиенты ---

class CreateClient(BaseModel):
    name: str
    phone: Optional[str] = None

class Deposit(BaseModel):
    amount: float

@app.get("/clients")
def get_clients():
    db = SessionLocal()
    clients = db.query(Client).all()
    result = [{"id": c.id, "name": c.name, "phone": c.phone, "balance": c.balance} for c in clients]
    db.close()
    return result

@app.post("/clients")
def create_client(data: CreateClient):
    db = SessionLocal()
    client = Client(name=data.name, phone=data.phone, balance=0.0)
    db.add(client)
    db.commit()
    result = {"id": client.id, "name": client.name, "phone": client.phone, "balance": client.balance}
    db.close()
    logging.info(f"Клиент создан: {client.name}")
    return result

@app.post("/clients/{client_id}/deposit")
def deposit(client_id: int, data: Deposit):
    db = SessionLocal()
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        db.close()
        raise HTTPException(status_code=404, detail="Клиент не найден")
    client.balance += data.amount
    transaction = Transaction(
        client_id=client_id,
        amount=data.amount,
        type="deposit"
    )
    db.add(transaction)
    db.commit()
    result = {"id": client.id, "name": client.name, "balance": client.balance}
    db.close()
    logging.info(f"Пополнение баланса клиента {client_id}: {data.amount}")
    return result

# --- Сессии ---

class StartSession(BaseModel):
    computer_id: int
    tariff_id: int
    client_id: Optional[int] = None

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
        client_id=data.client_id,
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
    if session.client_id:
        client = db.query(Client).filter(Client.id == session.client_id).first()
        if client:
            client.balance -= total
            transaction = Transaction(
                client_id=session.client_id,
                amount=-total,
                type="session"
            )
            db.add(transaction)
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
            "client_id": s.client_id,
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


@app.get("/reports/today")
def today_report():
    db = SessionLocal()
    today = datetime.datetime.utcnow().date()
    sessions = db.query(Session).filter(
        Session.ended_at != None,
        Session.started_at >= datetime.datetime(today.year, today.month, today.day)
    ).all()
    total = sum(s.total_amount or 0 for s in sessions)
    result = {
        "total_amount": round(total, 2),
        "sessions_count": len(sessions),
        "sessions": [
            {
                "session_id": s.id,
                "computer_id": s.computer_id,
                "client_id": s.client_id,
                "duration_minutes": round((s.ended_at - s.started_at).seconds / 60, 1),
                "total_amount": s.total_amount,
                "started_at": str(s.started_at),
                "ended_at": str(s.ended_at)
            }
            for s in sessions
        ]
    }
    db.close()
    return result


class CreateTariff(BaseModel):
    name: str
    price_per_hour: float

@app.get("/tariffs")
def get_tariffs():
    db = SessionLocal()
    tariffs = db.query(Tariff).all()
    result = [{"id": t.id, "name": t.name, "price_per_hour": t.price_per_hour} for t in tariffs]
    db.close()
    return result

@app.post("/tariffs")
def create_tariff(data: CreateTariff):
    db = SessionLocal()
    tariff = Tariff(name=data.name, price_per_hour=data.price_per_hour)
    db.add(tariff)
    db.commit()
    result = {"id": tariff.id, "name": tariff.name, "price_per_hour": tariff.price_per_hour}
    db.close()
    return result

@app.delete("/tariffs/{tariff_id}")
def delete_tariff(tariff_id: int):
    db = SessionLocal()
    tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
    if not tariff:
        db.close()
        raise HTTPException(status_code=404, detail="Тариф не найден")
    db.delete(tariff)
    db.commit()
    db.close()
    return {"ok": True}


class UpdateTariff(BaseModel):
    name: str
    price_per_hour: float

@app.put("/tariffs/{tariff_id}")
def update_tariff(tariff_id: int, data: UpdateTariff):
    db = SessionLocal()
    tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
    if not tariff:
        db.close()
        raise HTTPException(status_code=404, detail="Тариф не найден")
    tariff.name = data.name
    tariff.price_per_hour = data.price_per_hour
    db.commit()
    result = {"id": tariff.id, "name": tariff.name, "price_per_hour": tariff.price_per_hour}
    db.close()
    return result
