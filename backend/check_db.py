from database import SessionLocal, Computer

db = SessionLocal()
computers = db.query(Computer).all()
for c in computers:
    print(f"ПК {c.number}: {c.name} — статус: {c.status}, last_seen: {c.last_seen}")
db.close()
