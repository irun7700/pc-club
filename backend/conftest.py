import os
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from database import Base, engine, SessionLocal, User
from auth import hash_password

Base.metadata.create_all(bind=engine)

# Создаём owner для тестов
db = SessionLocal()
if not db.query(User).filter(User.username == "owner").first():
    db.add(User(username="owner", password_hash=hash_password("owner123"), role="owner"))
    db.commit()
db.close()
