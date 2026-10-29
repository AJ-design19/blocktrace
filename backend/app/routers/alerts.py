import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas, service
from ..database import get_db
from ..models import Alert, Transaction, User
from ..security import require_role

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _out(a: Alert) -> dict:
    return {"id": a.id, "token": a.token, "level": a.level, "score": a.score, "reasons": json.loads(a.reasons),
            "status": a.status, "assignee": a.assignee, "note": a.note, "created_at": a.created_at}


@router.get("", response_model=list[schemas.AlertOut])
def list_alerts(status: str | None = None, limit: int = Query(100, ge=1, le=500),
                db: Session = Depends(get_db), _: User = Depends(require_role("auditor"))):
    q = select(Alert).order_by(Alert.id.desc()).limit(limit)
    if status:
        q = q.where(Alert.status == status)
    return [_out(a) for a in db.execute(q).scalars()]


@router.patch("/{alert_id}", response_model=schemas.AlertOut)
def update_alert(alert_id: int, body: schemas.AlertUpdate, db: Session = Depends(get_db), user: User = Depends(require_role("auditor"))):
    a = db.get(Alert, alert_id)
    if not a:
        raise HTTPException(404, "Alert not found")
    a.status, a.note, a.assignee = body.status, body.note, user.username
    tx = db.execute(select(Transaction).where(Transaction.token == a.token)).scalar_one()
    if body.freeze:
        tx.status = "frozen"
    elif body.status == "dismissed":
        tx.status = "cleared"
    elif body.status == "resolved" and tx.status == "flagged":
        tx.status = "cleared"
    service.audit(db, user.username, "alert.update", a.token, f"{body.status} freeze={body.freeze}")
    db.commit()
    return _out(a)
