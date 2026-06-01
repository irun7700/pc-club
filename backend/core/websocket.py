import asyncio
import json
import logging
import datetime

from fastapi import WebSocket, WebSocketDisconnect
from database import SessionLocal, Computer, Session, Transaction
from auth import decode_token

connected_agents: dict = {}


async def agent_websocket(websocket: WebSocket, token: str = None):
    await websocket.accept()
    computer_id = None
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if not token:
                token = msg.get("token")
                if not token:
                    await websocket.send_text(json.dumps({"error": "token required"}))
                    await websocket.close()
                    return
                try:
                    decode_token(token)
                except Exception:
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
        try:
            computers = db.query(Computer).filter(Computer.status == "online").all()
            now = datetime.datetime.utcnow()

            for computer in computers:
                if computer.last_seen and (now - computer.last_seen).seconds > 15:
                    computer.status = "offline"

            active_sessions = db.query(Session).filter(Session.ended_at == None).all()
            for s in active_sessions:
                from database import Tariff
                tariff = db.query(Tariff).filter(Tariff.id == s.tariff_id).first()
                if tariff and tariff.duration_minutes:
                    elapsed = (now - s.started_at).seconds / 60
                    if elapsed >= tariff.duration_minutes:
                        duration = (now - s.started_at).seconds / 3600
                        total = tariff.total_price if tariff.total_price else round(duration * (tariff.price_per_hour or 0), 2)
                        s.ended_at = now
                        s.total_amount = total
                        if s.client_id:
                            from database import Client
                            client = db.query(Client).filter(Client.id == s.client_id).first()
                            if client:
                                if client.balance < total:
                                    total = client.balance
                                client.balance -= total
                                client.balance = round(max(client.balance, 0), 2)
                                db.add(Transaction(client_id=s.client_id, amount=-total, type="session"))
                        logging.info(f"Автозавершение сессии {s.id} на ПК {s.computer_id}")

            db.commit()
        finally:
            db.close()
