import asyncio
import logging
import os

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from database import init_db, SessionLocal, engine, User, AuditLog
from auth import hash_password
from core.websocket import agent_websocket, check_offline
from routers import clients, sessions, computers, tariffs, reports, users, bonus, audit

logging.basicConfig(
    filename="backend.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    try:
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

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.role == "owner").first()
        if not existing:
            u = User(
                username="owner",
                password_hash=hash_password(os.getenv("OWNER_PASSWORD", "owner123")),
                role="owner",
            )
            db.add(u)
            db.commit()
    finally:
        db.close()

    task = asyncio.create_task(check_offline())

    yield

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


limiter = Limiter(key_func=get_remote_address)

app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://pc-club-production.up.railway.app",
        "https://lavish-abundance-production-537b.up.railway.app",
        "http://localhost:5173",
    ],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(clients.router)
app.include_router(sessions.router)
app.include_router(computers.router)
app.include_router(tariffs.router)
app.include_router(reports.router)
app.include_router(users.router)
app.include_router(bonus.router)
app.include_router(audit.router)

app.add_api_websocket_route("/ws/agent", agent_websocket)


@app.get("/health")
def health():
    return {"status": "ok"}
