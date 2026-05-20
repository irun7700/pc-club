from database import SessionLocal, Computer

db = SessionLocal()
computer = Computer(name="ПК-1", number=1, status="offline")
db.add(computer)
db.commit()
print("ПК добавлен! ID:", computer.id)
db.close()
