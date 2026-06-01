from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from database import SessionLocal, BonusPromo
from core.deps import require_role

router = APIRouter(prefix="/bonus-promos", tags=["bonus"])


class CreateBonusPromo(BaseModel):
    name: str
    min_deposit: float
    bonus_amount: float
    max_bonus_percent: float = 50.0


@router.get("")
def get_bonus_promos(user=Depends(require_role("owner"))):
    db = SessionLocal()
    try:
        promos = db.query(BonusPromo).all()
        return [
            {"id": p.id, "name": p.name, "min_deposit": p.min_deposit,
             "bonus_amount": p.bonus_amount, "max_bonus_percent": p.max_bonus_percent, "is_active": p.is_active}
            for p in promos
        ]
    finally:
        db.close()


@router.post("")
def create_bonus_promo(data: CreateBonusPromo, user=Depends(require_role("owner"))):
    db = SessionLocal()
    try:
        promo = BonusPromo(
            name=data.name, min_deposit=data.min_deposit,
            bonus_amount=data.bonus_amount, max_bonus_percent=data.max_bonus_percent,
            is_active=0,
        )
        db.add(promo)
        db.commit()
        return {"id": promo.id, "name": promo.name, "min_deposit": promo.min_deposit,
                "bonus_amount": promo.bonus_amount, "max_bonus_percent": promo.max_bonus_percent, "is_active": promo.is_active}
    finally:
        db.close()


@router.put("/{promo_id}/toggle")
def toggle_bonus_promo(promo_id: int, user=Depends(require_role("owner"))):
    db = SessionLocal()
    try:
        promo = db.query(BonusPromo).filter(BonusPromo.id == promo_id).first()
        if not promo:
            raise HTTPException(status_code=404, detail="Акция не найдена")
        if not promo.is_active:
            db.query(BonusPromo).filter(BonusPromo.id != promo_id).update({"is_active": 0})
        promo.is_active = 0 if promo.is_active else 1
        db.commit()
        return {"ok": True, "is_active": promo.is_active}
    finally:
        db.close()


@router.put("/{promo_id}")
def update_bonus_promo(promo_id: int, data: CreateBonusPromo, user=Depends(require_role("owner"))):
    db = SessionLocal()
    try:
        promo = db.query(BonusPromo).filter(BonusPromo.id == promo_id).first()
        if not promo:
            raise HTTPException(status_code=404, detail="Акция не найдена")
        promo.name = data.name
        promo.min_deposit = data.min_deposit
        promo.bonus_amount = data.bonus_amount
        promo.max_bonus_percent = data.max_bonus_percent
        db.commit()
        return {"id": promo.id, "name": promo.name, "min_deposit": promo.min_deposit,
                "bonus_amount": promo.bonus_amount, "max_bonus_percent": promo.max_bonus_percent, "is_active": promo.is_active}
    finally:
        db.close()


@router.delete("/{promo_id}")
def delete_bonus_promo(promo_id: int, user=Depends(require_role("owner"))):
    db = SessionLocal()
    try:
        promo = db.query(BonusPromo).filter(BonusPromo.id == promo_id).first()
        if not promo:
            raise HTTPException(status_code=404, detail="Акция не найдена")
        db.delete(promo)
        db.commit()
        return {"ok": True}
    finally:
        db.close()
