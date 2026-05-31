from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from pydantic import validator
from fastapi.middleware.cors import CORSMiddleware
from database import init_db, SessionLocal, Computer, Session, Tariff, Client, Transaction, BonusPromo, engine
from pydantic import BaseModel
from typing import Optional
import datetime
import asyncio
import json
import logging
import os

logging.basicConfig(
    filename="backend.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://pc-club-production.up.railway.app", "https://lavish-abundance-production-537b.up.railway.app", "http://localhost:5173"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    allow_credentials=True,
)

@app.on_event("startup")
async def startup():
    init_db()
    # Миграции
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS bonus_balance FLOAT DEFAULT 0.0"))
            conn.execute(text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS birthday VARCHAR"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sessions_computer_id ON sessions(computer_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sessions_ended_at ON sessions(ended_at)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sessions_client_id ON sessions(client_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_transactions_client_id ON transactions(client_id)"))
            conn.execute(text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS is_blocked INTEGER DEFAULT 0"))
            conn.execute(text("UPDATE clients SET is_blocked = 0 WHERE is_blocked IS NULL"))
            conn.commit()
    except Exception as e:
        logging.warning(f"Migration warning: {e}")
    # Автосоздание owner если не существует
    db = SessionLocal()
    from auth import hash_password
    existing = db.query(User).filter(User.role == "owner").first()
    if not existing:
        u = User(username="owner", password_hash=hash_password(os.getenv("OWNER_PASSWORD", "owner123")), role="owner")
        db.add(u)
        db.commit()
    db.close()
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
    birthday: Optional[str] = None

    @validator("name")
    def name_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Имя не может быть пустым")
        return v.strip()

class Deposit(BaseModel):
    amount: float
    payment_method: str = "cash"  # cash, card, mixed
    cash_amount: float = None
    card_amount: float = None

@app.get("/clients")
def get_clients(limit: int = 100, offset: int = 0):
    db = SessionLocal()
    clients = db.query(Client).offset(offset).limit(limit).all()
    result = [{"id": c.id, "name": c.name, "phone": c.phone, "balance": c.balance, "bonus_balance": c.bonus_balance or 0, "birthday": c.birthday, "is_blocked": getattr(c, "is_blocked", 0) or 0} for c in clients]
    db.close()
    return result

@app.post("/clients")
def create_client(data: CreateClient):
    db = SessionLocal()
    client = Client(name=data.name, phone=data.phone, balance=0.0, birthday=data.birthday)
    db.add(client)
    db.commit()
    result = {"id": client.id, "name": client.name, "phone": client.phone, "balance": client.balance, "birthday": client.birthday}
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
        type="deposit",
        payment_method=data.payment_method,
        cash_amount=data.cash_amount,
        card_amount=data.card_amount
    )
    db.add(transaction)
    # Проверяем активные бонусные акции
    bonus_earned = 0
    promos = db.query(BonusPromo).filter(BonusPromo.is_active == 1).all()
    for promo in promos:
        if data.amount >= promo.min_deposit:
            client.bonus_balance += promo.bonus_amount
            bonus_earned += promo.bonus_amount
    db.commit()
    result = {"id": client.id, "name": client.name, "balance": client.balance, "bonus_balance": client.bonus_balance, "bonus_earned": bonus_earned}
    db.close()
    logging.info(f"Пополнение баланса клиента {client_id}: {data.amount} ({data.payment_method}), бонусы: {bonus_earned}")
    return result

# --- Сессии ---

class StartSession(BaseModel):
    computer_id: int
    tariff_id: int
    client_id: Optional[int] = None
    bonus_amount: float = 0

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
    # Проверка баланса клиента
    if data.client_id:
        client = db.query(Client).filter(Client.id == data.client_id).first()
        if client:
            # Списываем бонусы если указаны
            if data.bonus_amount > 0:
                if client.bonus_balance and client.bonus_balance >= data.bonus_amount:
                    client.bonus_balance -= data.bonus_amount
                else:
                    db.close()
                    raise HTTPException(status_code=400, detail=f"Недостаточно бонусов. Доступно: {client.bonus_balance or 0}")
            
            # Проверяем остаток деньгами
            remaining = (tariff.total_price or tariff.price_per_hour or 0) - data.bonus_amount
            if remaining > 0 and client.balance < remaining:
                db.close()
                raise HTTPException(status_code=400, detail=f"Недостаточно средств. Баланс: {client.balance} ₸, нужно: {remaining} ₸")
    # Проверка временного тарифа
    if tariff.type == "timed" and tariff.start_time and tariff.end_time:
        now_time = datetime.datetime.utcnow().strftime("%H:%M")
        if not (tariff.start_time <= now_time <= tariff.end_time):
            db.close()
            raise HTTPException(status_code=400, detail=f"Тариф доступен только с {tariff.start_time} до {tariff.end_time}")
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
        tariff = db.query(Tariff).filter(Tariff.id == s.tariff_id).first()
        result.append({
            "session_id": s.id,
            "computer_id": s.computer_id,
            "tariff_id": s.tariff_id,
            "client_id": s.client_id,
            "started_at": str(s.started_at),
            "duration_minutes": round(duration, 1),
            "tariff_duration": tariff.duration_minutes if tariff else None
        })
    db.close()
    return result

# Словарь подключённых агентов
connected_agents = {}

@app.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket, token: str = None):
    await websocket.accept()
    computer_id = None
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            # Проверка токена при первом сообщении
            if not token:
                token = msg.get("token")
                if not token:
                    await websocket.send_text(json.dumps({"error": "token required"}))
                    await websocket.close()
                    return
                try:
                    decode_token(token)
                except:
                    await websocket.send_text(json.dumps({"error": "invalid token"}))
                    await websocket.close()
                    return
            computer_id = msg.get("computer_id")
            event = msg.get("event")
            if event == "heartbeat" and computer_id:
                connected_agents[computer_id] = websocket
                db = SessionLocal()
                computer = db.query(Computer).filter(Computer.id == computer_id).first()
                if computer:
                    computer.status = "online"
                    computer.last_seen = datetime.datetime.utcnow()
                    db.commit()
                db.close()
            await websocket.send_text(json.dumps({"event": "heartbeat_ack", "status": "ok"}))
    except WebSocketDisconnect:
        if computer_id and computer_id in connected_agents:
            del connected_agents[computer_id]
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

        # Автозавершение сессий по истечении времени тарифа
        active_sessions = db.query(Session).filter(Session.ended_at == None).all()
        for s in active_sessions:
            tariff = db.query(Tariff).filter(Tariff.id == s.tariff_id).first()
            if tariff and tariff.duration_minutes:
                elapsed = (now - s.started_at).seconds / 60
                if elapsed >= tariff.duration_minutes:
                    duration = (now - s.started_at).seconds / 3600
                    total = round(duration * (tariff.price_per_hour or 0), 2)
                    if tariff.total_price:
                        total = tariff.total_price
                    s.ended_at = now
                    s.total_amount = total
                    if s.client_id:
                        client = db.query(Client).filter(Client.id == s.client_id).first()
                        if client:
                            if client.balance < total:
                                total = client.balance
                            client.balance -= total
                            client.balance = round(max(client.balance, 0), 2)
                            db.add(Transaction(client_id=s.client_id, amount=-total, type="session"))
                    logging.info(f"Автозавершение сессии {s.id} на ПК {s.computer_id}")
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

@app.get("/reports/full")
def full_report(date_from: str = None, date_to: str = None):
    db = SessionLocal()
    # Фильтр дат
    query = db.query(Session).filter(Session.ended_at != None)
    txn_query = db.query(Transaction)
    if date_from:
        dt_from = datetime.datetime.strptime(date_from, "%Y-%m-%d")
        query = query.filter(Session.started_at >= dt_from)
        txn_query = txn_query.filter(Transaction.created_at >= dt_from)
    if date_to:
        dt_to = datetime.datetime.strptime(date_to, "%Y-%m-%d") + datetime.timedelta(days=1)
        query = query.filter(Session.started_at < dt_to)
        txn_query = txn_query.filter(Transaction.created_at < dt_to)
    # Все завершённые сессии
    sessions = query.all()
    # Все транзакции
    transactions = txn_query.all()
    # Все компьютеры
    computers = db.query(Computer).all()
    # Все тарифы
    tariffs = db.query(Tariff).all()
    # Все клиенты
    clients = db.query(Client).all()
    # Все пользователи (сотрудники)
    users = db.query(User).all()

    # Выручка по дням
    revenue_by_day = {}
    for s in sessions:
        day = str(s.started_at.date())
        revenue_by_day[day] = round(revenue_by_day.get(day, 0) + (s.total_amount or 0), 2)

    # Популярные тарифы
    tariff_usage = {}
    for s in sessions:
        tariff_usage[s.tariff_id] = tariff_usage.get(s.tariff_id, 0) + 1
    popular_tariffs = []
    for t in tariffs:
        popular_tariffs.append({"id": t.id, "name": t.name, "count": tariff_usage.get(t.id, 0), "revenue": round(sum(s.total_amount or 0 for s in sessions if s.tariff_id == t.id), 2)})
    popular_tariffs.sort(key=lambda x: x["count"], reverse=True)

    # Способы оплаты
    payment_methods = {"cash": 0, "card": 0, "mixed": 0}
    for t in transactions:
        if t.type == "deposit" and t.payment_method:
            payment_methods[t.payment_method] = round(payment_methods.get(t.payment_method, 0) + t.amount, 2)

    # Активные клиенты (имеют хотя бы одну сессию)
    active_client_ids = set(s.client_id for s in sessions if s.client_id)
    active_clients = [{"id": c.id, "name": c.name, "sessions": len([s for s in sessions if s.client_id == c.id]), "total_spent": round(sum(s.total_amount or 0 for s in sessions if s.client_id == c.id), 2)} for c in clients if c.id in active_client_ids]
    active_clients.sort(key=lambda x: x["total_spent"], reverse=True)

    # Загрузка баланса по сотрудникам
    staff_deposits = []
    for u in users:
        user_txns = [t for t in transactions if t.type == "deposit"]
        staff_deposits.append({"id": u.id, "username": u.username, "role": u.role, "total_deposits": round(sum(t.amount for t in user_txns), 2)})

    # Выручка по ПК
    pc_revenue = []
    for c in computers:
        pc_sessions = [s for s in sessions if s.computer_id == c.id]
        pc_revenue.append({"id": c.id, "name": c.name, "sessions": len(pc_sessions), "revenue": round(sum(s.total_amount or 0 for s in pc_sessions), 2), "hours": round(sum((s.ended_at - s.started_at).seconds / 3600 for s in pc_sessions), 1)})
    pc_revenue.sort(key=lambda x: x["revenue"], reverse=True)

    result = {
        "total_revenue": round(sum(s.total_amount or 0 for s in sessions), 2),
        "total_sessions": len(sessions),
        "total_clients": len(clients),
        "revenue_by_day": [{"date": k, "revenue": v} for k, v in sorted(revenue_by_day.items())],
        "popular_tariffs": popular_tariffs,
        "payment_methods": payment_methods,
        "active_clients": active_clients[:10],
        "staff_deposits": staff_deposits,
        "pc_revenue": pc_revenue
    }
    db.close()
    return result


def tariff_to_dict(t):
    return {
        "id": t.id, "name": t.name, "type": t.type or "hourly",
        "price_per_hour": t.price_per_hour, "total_price": t.total_price,
        "duration_minutes": t.duration_minutes, "start_time": t.start_time, "end_time": t.end_time
    }

class CreateTariff(BaseModel):
    name: str
    type: str = "hourly"
    price_per_hour: float = None
    total_price: float = None
    duration_minutes: int = None
    start_time: str = None
    end_time: str = None

    @validator("price_per_hour", "total_price", pre=True, always=True)
    def price_must_be_positive(cls, v):
        if v is not None and v < 0:
            raise ValueError("Цена не может быть отрицательной")
        return v

@app.get("/tariffs")
def get_tariffs():
    db = SessionLocal()
    tariffs = db.query(Tariff).all()
    result = [tariff_to_dict(t) for t in tariffs]
    db.close()
    return result

@app.post("/tariffs")
def create_tariff(data: CreateTariff):
    db = SessionLocal()
    tariff = Tariff(
        name=data.name, type=data.type,
        price_per_hour=data.price_per_hour, total_price=data.total_price,
        duration_minutes=data.duration_minutes, start_time=data.start_time, end_time=data.end_time
    )
    db.add(tariff)
    db.commit()
    result = tariff_to_dict(tariff)
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
    type: str = "hourly"
    price_per_hour: float = None
    total_price: float = None
    duration_minutes: int = None
    start_time: str = None
    end_time: str = None

@app.put("/tariffs/{tariff_id}")
def update_tariff(tariff_id: int, data: UpdateTariff):
    db = SessionLocal()
    tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
    if not tariff:
        db.close()
        raise HTTPException(status_code=404, detail="Тариф не найден")
    tariff.name = data.name; tariff.type = data.type
    tariff.price_per_hour = data.price_per_hour; tariff.total_price = data.total_price
    tariff.duration_minutes = data.duration_minutes; tariff.start_time = data.start_time; tariff.end_time = data.end_time
    db.commit()
    result = tariff_to_dict(tariff)
    db.close()
    return result



# --- Авторизация ---
from auth import hash_password, verify_password, create_token, decode_token
from database import User
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = decode_token(credentials.credentials)
        return payload
    except:
        raise HTTPException(status_code=401, detail="Неверный токен")

def require_role(*roles):
    def checker(user=Depends(get_current_user)):
        if user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Нет доступа")
        return user
    return checker

@app.post("/computers/{computer_id}/command")
async def send_command(computer_id: int, data: dict, user=Depends(require_role("owner", "manager"))):
    ws = connected_agents.get(computer_id)
    if not ws:
        raise HTTPException(status_code=404, detail="ПК не подключён")
    await ws.send_text(json.dumps({"event": "command", "command": data.get("command")}))
    return {"ok": True}

# --- Бонусные акции ---

class CreateBonusPromo(BaseModel):
    name: str
    min_deposit: float
    bonus_amount: float
    max_bonus_percent: float = 50.0



@app.get("/clients/{client_id}/transactions")
def get_client_transactions(client_id: int, user=Depends(get_current_user)):
    db = SessionLocal()
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        db.close()
        raise HTTPException(status_code=404, detail="Клиент не найден")
    txns = db.query(Transaction).filter(Transaction.client_id == client_id).order_by(Transaction.created_at.desc()).limit(20).all()
    result = [{"id": t.id, "amount": t.amount, "type": t.type, "payment_method": t.payment_method, "created_at": str(t.created_at)} for t in txns]
    db.close()
    return result

@app.put("/clients/{client_id}/block")
def toggle_block_client(client_id: int, user=Depends(require_role("owner", "manager"))):
    db = SessionLocal()
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        db.close()
        raise HTTPException(status_code=404, detail="Клиент не найден")
    client.is_blocked = 0 if client.is_blocked else 1
    db.commit()
    db.close()
    return {"ok": True, "is_blocked": client.is_blocked}

@app.get("/bonus-promos")
def get_bonus_promos(user=Depends(require_role("owner"))):
    db = SessionLocal()
    promos = db.query(BonusPromo).all()
    result = [{"id": p.id, "name": p.name, "min_deposit": p.min_deposit, "bonus_amount": p.bonus_amount, "max_bonus_percent": p.max_bonus_percent, "is_active": p.is_active} for p in promos]
    db.close()
    return result

@app.post("/bonus-promos")
def create_bonus_promo(data: CreateBonusPromo, user=Depends(require_role("owner"))):
    db = SessionLocal()
    # Новая акция создаётся неактивной
    promo = BonusPromo(name=data.name, min_deposit=data.min_deposit, bonus_amount=data.bonus_amount, max_bonus_percent=data.max_bonus_percent, is_active=0)
    db.add(promo)
    db.commit()
    result = {"id": promo.id, "name": promo.name, "min_deposit": promo.min_deposit, "bonus_amount": promo.bonus_amount, "max_bonus_percent": promo.max_bonus_percent, "is_active": promo.is_active}
    db.close()
    return result

@app.put("/bonus-promos/{promo_id}/toggle")
def toggle_bonus_promo(promo_id: int, user=Depends(require_role("owner"))):
    db = SessionLocal()
    promo = db.query(BonusPromo).filter(BonusPromo.id == promo_id).first()
    if not promo:
        db.close()
        raise HTTPException(status_code=404, detail="Акция не найдена")
    if not promo.is_active:
        # Отключаем все остальные акции
        db.query(BonusPromo).filter(BonusPromo.id != promo_id).update({"is_active": 0})
    promo.is_active = 0 if promo.is_active else 1
    db.commit()
    db.close()
    return {"ok": True, "is_active": promo.is_active}

@app.put("/bonus-promos/{promo_id}")
def update_bonus_promo(promo_id: int, data: CreateBonusPromo, user=Depends(require_role("owner"))):
    db = SessionLocal()
    promo = db.query(BonusPromo).filter(BonusPromo.id == promo_id).first()
    if not promo:
        db.close()
        raise HTTPException(status_code=404, detail="Акция не найдена")
    promo.name = data.name
    promo.min_deposit = data.min_deposit
    promo.bonus_amount = data.bonus_amount
    promo.max_bonus_percent = data.max_bonus_percent
    db.commit()
    result = {"id": promo.id, "name": promo.name, "min_deposit": promo.min_deposit, "bonus_amount": promo.bonus_amount, "max_bonus_percent": promo.max_bonus_percent, "is_active": promo.is_active}
    db.close()
    return result

@app.delete("/bonus-promos/{promo_id}")
def delete_bonus_promo(promo_id: int, user=Depends(require_role("owner"))):
    db = SessionLocal()
    promo = db.query(BonusPromo).filter(BonusPromo.id == promo_id).first()
    if not promo:
        db.close()
        raise HTTPException(status_code=404, detail="Акция не найдена")
    db.delete(promo)
    db.commit()
    db.close()
    return {"ok": True}

class LoginData(BaseModel):
    username: str
    password: str

class CreateUser(BaseModel):
    username: str
    password: str
    role: str

@app.post("/auth/login")
@limiter.limit("5/minute")
def login(request: Request, data: LoginData):
    db = SessionLocal()
    user = db.query(User).filter(User.username == data.username).first()
    db.close()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    token = create_token({"id": user.id, "username": user.username, "role": user.role})
    return {"token": token, "role": user.role, "username": user.username}

@app.get("/auth/me")
def me(user=Depends(get_current_user)):
    return user

@app.get("/users")
def get_users(user=Depends(require_role("owner"))):
    db = SessionLocal()
    users = db.query(User).all()
    result = [{"id": u.id, "username": u.username, "role": u.role} for u in users]
    db.close()
    return result

@app.post("/users")
def create_user(data: CreateUser, user=Depends(require_role("owner"))):
    db = SessionLocal()
    existing = db.query(User).filter(User.username == data.username).first()
    if existing:
        db.close()
        raise HTTPException(status_code=400, detail="Пользователь уже существует")
    new_user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        role=data.role,
        created_by=user["id"]
    )
    db.add(new_user)
    db.commit()
    result = {"id": new_user.id, "username": new_user.username, "role": new_user.role}
    db.close()
    return result

@app.delete("/users/{user_id}")
def delete_user(user_id: int, user=Depends(require_role("owner"))):
    db = SessionLocal()
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        db.close()
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    db.delete(u)
    db.commit()
    db.close()
    return {"ok": True}








class CreateComputer(BaseModel):
    name: str
    number: int

@app.post("/computers")
def create_computer(data: CreateComputer, user=Depends(require_role("owner", "manager"))):
    db = SessionLocal()
    computer = Computer(name=data.name, number=data.number, status="offline")
    db.add(computer)
    db.commit()
    result = {"id": computer.id, "name": computer.name, "number": computer.number}
    db.close()
    return result

@app.delete("/computers/{computer_id}")
def delete_computer(computer_id: int, user=Depends(require_role("owner"))):
    db = SessionLocal()
    computer = db.query(Computer).filter(Computer.id == computer_id).first()
    if not computer:
        db.close()
        raise HTTPException(status_code=404, detail="ПК не найден")
    db.delete(computer)
    db.commit()
    db.close()
    return {"ok": True}


class UpdateUser(BaseModel):
    password: str = None
    username: str = None

@app.put("/users/{user_id}")
def update_user(user_id: int, data: UpdateUser, user=Depends(require_role("owner"))):
    db = SessionLocal()
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        db.close()
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if data.password:
        u.password_hash = hash_password(data.password)
    if data.username:
        u.username = data.username
    db.commit()
    result = {"id": u.id, "username": u.username, "role": u.role}
    db.close()
    return result
    u = User(username="owner", password_hash=hash_password(os.getenv("OWNER_PASSWORD", "owner123")), role="owner")
    db.add(u)
    db.commit()
    db.close()
    return {"status": "created", "message": "Owner создан с паролем owner123"}
