from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional

from database import SessionLocal, User
from auth import hash_password, verify_password, create_token
from core.deps import get_current_user, require_role

router = APIRouter(tags=["auth"])


class LoginData(BaseModel):
    username: str
    password: str


class CreateUser(BaseModel):
    username: str
    password: str
    role: str


class UpdateUser(BaseModel):
    password: Optional[str] = None
    username: Optional[str] = None


@router.post("/auth/login")
def login(request: Request, data: LoginData):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == data.username).first()
        if not user or not verify_password(data.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Неверный логин или пароль")
        token = create_token({"id": user.id, "username": user.username, "role": user.role})
        return {"token": token, "role": user.role, "username": user.username}
    finally:
        db.close()


@router.get("/auth/me")
def me(user=Depends(get_current_user)):
    return user


@router.get("/users")
def get_users(user=Depends(require_role("owner"))):
    db = SessionLocal()
    try:
        users = db.query(User).all()
        return [{"id": u.id, "username": u.username, "role": u.role} for u in users]
    finally:
        db.close()


@router.post("/users")
def create_user(data: CreateUser, user=Depends(require_role("owner"))):
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == data.username).first()
        if existing:
            raise HTTPException(status_code=400, detail="Пользователь уже существует")
        new_user = User(
            username=data.username,
            password_hash=hash_password(data.password),
            role=data.role,
            created_by=user["id"],
        )
        db.add(new_user)
        db.commit()
        return {"id": new_user.id, "username": new_user.username, "role": new_user.role}
    finally:
        db.close()


@router.put("/users/{user_id}")
def update_user(user_id: int, data: UpdateUser, user=Depends(require_role("owner"))):
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.id == user_id).first()
        if not u:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        if data.password:
            u.password_hash = hash_password(data.password)
        if data.username:
            u.username = data.username
        db.commit()
        return {"id": u.id, "username": u.username, "role": u.role}
    finally:
        db.close()


@router.delete("/users/{user_id}")
def delete_user(user_id: int, user=Depends(require_role("owner"))):
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.id == user_id).first()
        if not u:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        db.delete(u)
        db.commit()
        return {"ok": True}
    finally:
        db.close()
