import logging
import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from database import SessionLocal, Computer, Session, Tariff, Client, Transaction
from core.audit import log_action

router = APIRouter(prefix="/sessions", tags=["sessions"])


class StartSession(BaseModel):
    computer_id: int
    tariff_id: int
    client_id: Optional[int] = None
    bonus_amount: float = 0
    purchased_minutes: Optional[int] = None


class StopSession(BaseModel):
    session_id: int


@router.post("/start")
def start_session(data: StartSession):
    db = SessionLocal()
    try:
        computer = db.query(Computer).filter(
    Computer.id == data.computer_id
).with_for_update().first()
        if not computer:
            raise HTTPException(status_code=404, detail="ПК не найден")

        active = db.query(Session).filter(
            Session.computer_id == data.computer_id,
            Session.ended_at == None,
        ).with_for_update().first()
        if active:
            raise HTTPException(status_code=400, detail="На этом ПК уже идёт сессия")

        tariff = db.query(Tariff).filter(Tariff.id == data.tariff_id).first()
        if not tariff:
            raise HTTPException(status_code=404, detail="Тариф не найден")

        if data.client_id:
            client = db.query(Client).filter(
    Client.id == data.client_id
).first()
            if client:
                if client.is_blocked:
                    raise HTTPException(status_code=400, detail="Клиент заблокирован")
                if data.bonus_amount > 0:
                    if client.bonus_balance and client.bonus_balance >= data.bonus_amount:
                        client.bonus_balance -= data.bonus_amount
                    else:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Недостаточно бонусов. Доступно: {client.bonus_balance or 0}",
                        )
                remaining = (tariff.total_price or tariff.price_per_hour or 0) - data.bonus_amount
                if remaining > 0 and client.balance < remaining:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Недостаточно средств. Баланс: {client.balance} ₸, нужно: {remaining} ₸",
                    )
                # Списываем сразу при старте
                prepaid = 0
                if tariff.total_price:
                    prepaid = remaining  # пакетный — фиксированная цена
                elif tariff.duration_minutes and tariff.price_per_hour:
                    prepaid = round(tariff.price_per_hour * tariff.duration_minutes / 60, 2) - data.bonus_amount
                    prepaid = max(prepaid, 0)
                elif data.purchased_minutes and tariff.price_per_hour:
                    prepaid = round(tariff.price_per_hour * data.purchased_minutes / 60, 2) - data.bonus_amount
                    prepaid = max(prepaid, 0)
                if prepaid > 0:
                    client.balance -= prepaid
                    db.add(Transaction(
                        client_id=data.client_id,
                        amount=-prepaid,
                        type="session"
                    ))

        if tariff.type == "timed" and tariff.start_time and tariff.end_time:
            now_time = datetime.datetime.utcnow().strftime("%H:%M")
            if not (tariff.start_time <= now_time <= tariff.end_time):
                raise HTTPException(
                    status_code=400,
                    detail=f"Тариф доступен только с {tariff.start_time} до {tariff.end_time}",
                )

        session = Session(
            computer_id=data.computer_id,
            tariff_id=data.tariff_id,
            client_id=data.client_id,
            started_at=datetime.datetime.utcnow(),
            purchased_minutes=data.purchased_minutes,
        )
        db.add(session)
        db.commit()
        logging.info(f"Сессия {session.id} начата на ПК {data.computer_id}")
        log_action(None, "start_session", f"session_id={session.id} computer_id={data.computer_id} tariff_id={data.tariff_id}")
        return {"session_id": session.id, "started_at": str(session.started_at)}
    finally:
        db.close()


@router.post("/stop")
def stop_session(data: StopSession):
    db = SessionLocal()
    try:
        session = db.query(Session).filter(
    Session.id == data.session_id,
    Session.ended_at == None,
).with_for_update().first()
        if not session:
            raise HTTPException(status_code=404, detail="Активная сессия не найдена")

        tariff = db.query(Tariff).filter(Tariff.id == session.tariff_id).first()
        now = datetime.datetime.utcnow()
        duration = (now - session.started_at).seconds / 3600

        # Уже списан при старте (пакетный или почасовой с purchased_minutes)
        prepaid_at_start = tariff.total_price or tariff.duration_minutes or session.purchased_minutes
        if prepaid_at_start:
            total = tariff.total_price or round((tariff.price_per_hour or 0) * (session.purchased_minutes or tariff.duration_minutes or 0) / 60, 2)
            session.ended_at = now
            session.total_amount = total
        else:
            # Чистый почасовой — списываем по факту
            total = round(duration * (tariff.price_per_hour or 0), 2)
            session.ended_at = now
            session.total_amount = total
            if session.client_id:
                client = db.query(Client).filter(Client.id == session.client_id).with_for_update().first()
                if client:
                    client.balance -= total
                    db.add(Transaction(client_id=session.client_id, amount=-total, type="session"))

        db.commit()
        logging.info(f"Сессия {session.id} завершена, сумма: {total}")
        log_action(None, "stop_session", f"session_id={session.id} total={total}")
        return {
            "session_id": session.id,
            "duration_minutes": round(duration * 60, 1),
            "total_amount": total,
        }
    finally:
        db.close()


@router.get("/active")
def get_active_sessions():
    db = SessionLocal()
    try:
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
                "tariff_duration": tariff.duration_minutes if tariff else None,
            })
        return result
    finally:
        db.close()


@router.get("")
def get_sessions(limit: int = 50, offset: int = 0):
    db = SessionLocal()
    try:
        total = db.query(Session).count()
        sessions = (
            db.query(Session)
            .order_by(Session.started_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "sessions": [
                {
                    "session_id": s.id,
                    "computer_id": s.computer_id,
                    "tariff_id": s.tariff_id,
                    "client_id": s.client_id,
                    "started_at": str(s.started_at),
                    "ended_at": str(s.ended_at) if s.ended_at else None,
                    "total_amount": s.total_amount,
                    "duration_minutes": round((s.ended_at - s.started_at).seconds / 60, 1) if s.ended_at else None,
                }
                for s in sessions
            ],
        }
    finally:
        db.close()
