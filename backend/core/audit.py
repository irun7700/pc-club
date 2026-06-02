from database import SessionLocal, AuditLog


def log_action(user: dict, action: str, details: str = None):
    db = SessionLocal()
    try:
        entry = AuditLog(
            user_id=user.get("id") if user else None,
            username=user.get("username") if user else "system",
            action=action,
            details=details,
        )
        db.add(entry)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
