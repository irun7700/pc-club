import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, validator
from typing import Optional

from database import SessionLocal, Client, Transaction, BonusPromo
from core.deps import get_current_user, require_role

router = APIRouter(prefix="/clients", tags=["clients"])


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
    payment_method: str = "cash"
    cash_amount: Optional[float] = None
    card_amount: Optional[float] = None


@router.get("")
def get_clients(limit: int = 100, offset: int = 0):
    db = SessionLocal()
    try:
        clients = db.query(Client).offset(offset).limit(limit).all()
        return [
            {
                "id": c.id, "name": c.name, "phone": c.phone,
                "balance": c.balance, "bonus_balance": c.bonus_balance or 0,
                "birthday": c.birthday, "is_blocked": getattr(c, "is_blocked", 0) or 0,
            }
            for c in clients
        ]
    finally:
        db.close()


@router.post("")
def create_client(data: CreateClient):
    db = SessionLocal()
    try:
        client = Client(name=data.name, phone=data.phone, balance=0.0, birthday=data.birthday)
        db.add(client)
        db.commit()
        logging.info(f"Клиент создан: {client.name}")
        return {"id": client.id, "name": client.name, "phone": client.phone, "balance": client.balance, "birthday": client.birthday}
    finally:
        db.close()


@router.post("/{client_id}/deposit")
def deposit(client_id: int, data: Deposit):
    db = SessionLocal()
    try:
        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="Клиент не найден")

        client.balance += data.amount
        transaction = Transaction(
            client_id=client_id,
            amount=data.amount,
            type="deposit",
            payment_method=data.payment_method,
            cash_amount=data.cash_amount,
            card_amount=data.card_amount,
        )
        db.add(transaction)

        bonus_earned = 0
        promos = db.query(BonusPromo).filter(BonusPromo.is_active == 1).all()
        for promo in promos:
            if data.amount >= promo.min_deposit:
                client.bonus_balance += promo.bonus_amount
                bonus_earned += promo.bonus_amount

        db.commit()
        logging.info(f"Пополнение клиента {client_id}: {data.amount} ({data.payment_method}), бонусы: {bonus_earned}")
        return {
            "id": client.id, "name": client.name,
            "balance": client.balance, "bonus_balance": client.bonus_balance,
            "bonus_earned": bonus_earned,
        }
    finally:
        db.close()


@router.get("/{client_id}/transactions")
def get_client_transactions(client_id: int, user=Depends(get_current_user)):
    db = SessionLocal()
    try:
        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="Клиент не найден")
        txns = (
            db.query(Transaction)
            .filter(Transaction.client_id == client_id)
            .order_by(Transaction.created_at.desc())
            .limit(20)
            .all()
        )
        return [
            {"id": t.id, "amount": t.amount, "type": t.type,
             "payment_method": t.payment_method, "created_at": str(t.created_at)}
            for t in txns
        ]
    finally:
        db.close()


@router.put("/{client_id}/block")
def toggle_block_client(client_id: int, user=Depends(require_role("owner", "manager"))):
    db = SessionLocal()
    try:
        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="Клиент не найден")
        client.is_blocked = 0 if client.is_blocked else 1
        db.commit()
        return {"ok": True, "is_blocked": client.is_blocked}
    finally:
        db.close()
