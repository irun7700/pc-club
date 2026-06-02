import datetime
from fastapi import APIRouter, Depends
from database import SessionLocal, AuditLog
from core.deps import require_role

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def get_audit_log(limit: int = 100, offset: int = 0, user=Depends(require_role("owner"))):
    db = SessionLocal()
    try:
        logs = (
            db.query(AuditLog)
            .order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [
            {
                "id": l.id,
                "user_id": l.user_id,
                "username": l.username,
                "action": l.action,
                "details": l.details,
                "created_at": str(l.created_at),
            }
            for l in logs
        ]
    finally:
        db.close()
