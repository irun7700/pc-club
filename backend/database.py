from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./club.db")

# PostgreSQL совместимость
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if DATABASE_URL.startswith("postgresql://"):
    engine = create_engine(DATABASE_URL)
else:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()

class Computer(Base):
    __tablename__ = "computers"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    number = Column(Integer, nullable=False)
    status = Column(String, default="offline")
    last_seen = Column(DateTime, nullable=True)

class Tariff(Base):
    __tablename__ = "tariffs"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    type = Column(String, default="hourly")  # hourly, package, timed
    price_per_hour = Column(Float, nullable=True)   # для почасового
    total_price = Column(Float, nullable=True)       # для пакета и временного
    duration_minutes = Column(Integer, nullable=True) # для пакета
    start_time = Column(String, nullable=True)        # для временного, напр. "08:00"
    end_time = Column(String, nullable=True)          # для временного, напр. "12:00"

class Client(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    balance = Column(Float, default=0.0)
    bonus_balance = Column(Float, default=0.0)
    birthday = Column(String, nullable=True)
    is_blocked = Column(Integer, default=0)

class BonusPromo(Base):
    __tablename__ = "bonus_promos"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    min_deposit = Column(Float, nullable=False)   # минимальная сумма пополнения
    bonus_amount = Column(Float, nullable=False)  # сколько бонусов начислить
    max_bonus_percent = Column(Float, default=50.0)  # макс % оплаты бонусами
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True)
    computer_id = Column(Integer, ForeignKey("computers.id"))
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)
    tariff_id = Column(Integer, ForeignKey("tariffs.id"))
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    total_amount = Column(Float, nullable=True)
    purchased_minutes = Column(Integer, nullable=True)

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    amount = Column(Float, nullable=False)
    type = Column(String, nullable=False)
    payment_method = Column(String, nullable=True)  # cash, card, mixed
    cash_amount = Column(Float, nullable=True)
    card_amount = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # owner, manager, admin
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)

class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True)
    username = Column(String, nullable=True)
    action = Column(String)
    details = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
