from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime

DATABASE_URL = "sqlite:///./club.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)
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
    price_per_hour = Column(Float, nullable=False)

class Client(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    balance = Column(Float, default=0.0)

class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True)
    computer_id = Column(Integer, ForeignKey("computers.id"))
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)
    tariff_id = Column(Integer, ForeignKey("tariffs.id"))
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    total_amount = Column(Float, nullable=True)

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    amount = Column(Float, nullable=False)
    type = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)
