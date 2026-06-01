from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, validator
from typing import Optional

from database import SessionLocal, Tariff

router = APIRouter(prefix="/tariffs", tags=["tariffs"])


def tariff_to_dict(t):
    return {
        "id": t.id, "name": t.name, "type": t.type or "hourly",
        "price_per_hour": t.price_per_hour, "total_price": t.total_price,
        "duration_minutes": t.duration_minutes, "start_time": t.start_time, "end_time": t.end_time,
    }


class CreateTariff(BaseModel):
    name: str
    type: str = "hourly"
    price_per_hour: Optional[float] = None
    total_price: Optional[float] = None
    duration_minutes: Optional[int] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None

    @validator("price_per_hour", "total_price", pre=True, always=True)
    def price_must_be_positive(cls, v):
        if v is not None and v < 0:
            raise ValueError("Цена не может быть отрицательной")
        return v


class UpdateTariff(CreateTariff):
    pass


@router.get("")
def get_tariffs():
    db = SessionLocal()
    try:
        tariffs = db.query(Tariff).all()
        return [tariff_to_dict(t) for t in tariffs]
    finally:
        db.close()


@router.post("")
def create_tariff(data: CreateTariff):
    db = SessionLocal()
    try:
        tariff = Tariff(
            name=data.name, type=data.type,
            price_per_hour=data.price_per_hour, total_price=data.total_price,
            duration_minutes=data.duration_minutes, start_time=data.start_time, end_time=data.end_time,
        )
        db.add(tariff)
        db.commit()
        return tariff_to_dict(tariff)
    finally:
        db.close()


@router.put("/{tariff_id}")
def update_tariff(tariff_id: int, data: UpdateTariff):
    db = SessionLocal()
    try:
        tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
        if not tariff:
            raise HTTPException(status_code=404, detail="Тариф не найден")
        tariff.name = data.name
        tariff.type = data.type
        tariff.price_per_hour = data.price_per_hour
        tariff.total_price = data.total_price
        tariff.duration_minutes = data.duration_minutes
        tariff.start_time = data.start_time
        tariff.end_time = data.end_time
        db.commit()
        return tariff_to_dict(tariff)
    finally:
        db.close()


@router.delete("/{tariff_id}")
def delete_tariff(tariff_id: int):
    db = SessionLocal()
    try:
        tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
        if not tariff:
            raise HTTPException(status_code=404, detail="Тариф не найден")
        db.delete(tariff)
        db.commit()
        return {"ok": True}
    finally:
        db.close()
