import datetime
from fastapi import APIRouter

from database import SessionLocal, Session, Transaction, Computer, Tariff, Client, User

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/today")
def today_report():
    db = SessionLocal()
    try:
        today = datetime.datetime.utcnow().date()
        sessions = db.query(Session).filter(
            Session.ended_at != None,
            Session.started_at >= datetime.datetime(today.year, today.month, today.day),
        ).all()
        total = sum(s.total_amount or 0 for s in sessions)
        return {
            "total_amount": round(total, 2),
            "sessions_count": len(sessions),
            "sessions": [
                {
                    "session_id": s.id,
                    "computer_id": s.computer_id,
                    "client_id": s.client_id,
                    "duration_minutes": round((s.ended_at - s.started_at).seconds / 60, 1),
                    "total_amount": s.total_amount,
                    "started_at": str(s.started_at),
                    "ended_at": str(s.ended_at),
                }
                for s in sessions
            ],
        }
    finally:
        db.close()


@router.get("/full")
def full_report(date_from: str = None, date_to: str = None):
    db = SessionLocal()
    try:
        query = db.query(Session).filter(Session.ended_at != None)
        txn_query = db.query(Transaction)

        if date_from:
            dt_from = datetime.datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(Session.started_at >= dt_from)
            txn_query = txn_query.filter(Transaction.created_at >= dt_from)
        if date_to:
            dt_to = datetime.datetime.strptime(date_to, "%Y-%m-%d") + datetime.timedelta(days=1)
            query = query.filter(Session.started_at < dt_to)
            txn_query = txn_query.filter(Transaction.created_at < dt_to)

        sessions = query.all()
        transactions = txn_query.all()
        computers = db.query(Computer).all()
        tariffs = db.query(Tariff).all()
        clients = db.query(Client).all()
        users = db.query(User).all()

        revenue_by_day: dict = {}
        for s in sessions:
            day = str(s.started_at.date())
            revenue_by_day[day] = round(revenue_by_day.get(day, 0) + (s.total_amount or 0), 2)

        tariff_usage: dict = {}
        for s in sessions:
            tariff_usage[s.tariff_id] = tariff_usage.get(s.tariff_id, 0) + 1
        popular_tariffs = sorted(
            [
                {
                    "id": t.id, "name": t.name,
                    "count": tariff_usage.get(t.id, 0),
                    "revenue": round(sum(s.total_amount or 0 for s in sessions if s.tariff_id == t.id), 2),
                }
                for t in tariffs
            ],
            key=lambda x: x["count"],
            reverse=True,
        )

        payment_methods: dict = {"cash": 0, "card": 0, "mixed": 0}
        for t in transactions:
            if t.type == "deposit" and t.payment_method:
                payment_methods[t.payment_method] = round(payment_methods.get(t.payment_method, 0) + t.amount, 2)

        active_client_ids = {s.client_id for s in sessions if s.client_id}
        active_clients = sorted(
            [
                {
                    "id": c.id, "name": c.name,
                    "sessions": len([s for s in sessions if s.client_id == c.id]),
                    "total_spent": round(sum(s.total_amount or 0 for s in sessions if s.client_id == c.id), 2),
                }
                for c in clients if c.id in active_client_ids
            ],
            key=lambda x: x["total_spent"],
            reverse=True,
        )

        deposit_txns = [t for t in transactions if t.type == "deposit"]
        staff_deposits = [
            {
                "id": u.id, "username": u.username, "role": u.role,
                "total_deposits": round(sum(t.amount for t in deposit_txns), 2),
            }
            for u in users
        ]

        pc_revenue = sorted(
            [
                {
                    "id": c.id, "name": c.name,
                    "sessions": len([s for s in sessions if s.computer_id == c.id]),
                    "revenue": round(sum(s.total_amount or 0 for s in sessions if s.computer_id == c.id), 2),
                    "hours": round(sum((s.ended_at - s.started_at).seconds / 3600 for s in sessions if s.computer_id == c.id), 1),
                }
                for c in computers
            ],
            key=lambda x: x["revenue"],
            reverse=True,
        )

        return {
            "total_revenue": round(sum(s.total_amount or 0 for s in sessions), 2),
            "total_sessions": len(sessions),
            "total_clients": len(clients),
            "revenue_by_day": [{"date": k, "revenue": v} for k, v in sorted(revenue_by_day.items())],
            "popular_tariffs": popular_tariffs,
            "payment_methods": payment_methods,
            "active_clients": active_clients[:10],
            "staff_deposits": staff_deposits,
            "pc_revenue": pc_revenue,
        }
    finally:
        db.close()
