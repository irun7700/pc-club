import json
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from database import SessionLocal, Computer
from core.deps import require_role
from core.websocket import connected_agents

router = APIRouter(prefix="/computers", tags=["computers"])


class CreateComputer(BaseModel):
    name: str
    number: int


@router.get("")
def get_computers(name: str = None, status: str = None):
    db = SessionLocal()
    try:
        query = db.query(Computer)
        if name:
            query = query.filter(Computer.name.ilike(f"%{name}%"))
        if status:
            query = query.filter(Computer.status == status)
        computers = query.all()
        return [{"id": c.id, "name": c.name, "status": c.status, "last_seen": str(c.last_seen)} for c in computers]
    finally:
        db.close()


@router.post("")
def create_computer(data: CreateComputer, user=Depends(require_role("owner", "manager"))):
    db = SessionLocal()
    try:
        computer = Computer(name=data.name, number=data.number, status="offline")
        db.add(computer)
        db.commit()
        return {"id": computer.id, "name": computer.name, "number": computer.number}
    finally:
        db.close()


@router.delete("/{computer_id}")
def delete_computer(computer_id: int, user=Depends(require_role("owner"))):
    db = SessionLocal()
    try:
        computer = db.query(Computer).filter(Computer.id == computer_id).first()
        if not computer:
            raise HTTPException(status_code=404, detail="ПК не найден")
        db.delete(computer)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.post("/{computer_id}/command")
async def send_command(computer_id: int, data: dict, user=Depends(require_role("owner", "manager"))):
    ws = connected_agents.get(computer_id)
    if not ws:
        raise HTTPException(status_code=404, detail="ПК не подключён")
    await ws.send_text(json.dumps({"event": "command", "command": data.get("command")}))
    return {"ok": True}
