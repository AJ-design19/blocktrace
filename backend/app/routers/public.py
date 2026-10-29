"""Citizen-facing transparency endpoints. No login. Only non-sensitive fields."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import service
from ..database import get_db
from ..models import Transaction
from ..schemas import ScoreRequest
from ..security import require_role
from ..models import User

router = APIRouter(tags=["public"])
METRICS = Path(__file__).resolve().parents[2] / "ml" / "artifacts" / "metrics.json"


@router.get("/public/verify/{token}")
def verify_token(token: str, db: Session = Depends(get_db)):
    t = db.execute(select(Transaction).where(Transaction.token == token)).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "No such token")
    chain = service.verify_chain(db)
    trace = service.trace(db, token)
    return {"token": t.token, "sender": t.sender, "receiver": t.receiver, "amount": t.amount_paise / 100, "ts": t.ts,
            "purpose": t.purpose, "status": t.status, "ledger_valid": chain["valid"], "hops_downstream": trace["summary"]["hops"],
            "final_recipients": trace["summary"]["final_recipients"], "anchored": t.batch_id is not None}


@router.get("/public/summary")
def public_summary(db: Session = Depends(get_db)):
    n, vol = db.execute(select(func.count(Transaction.id), func.coalesce(func.sum(Transaction.amount_paise), 0))).one()
    return {"transactions_recorded": n, "total_volume": vol / 100, "ledger_valid": service.verify_chain(db)["valid"]}


@router.get("/ml/metrics")
def ml_metrics():
    if METRICS.exists():
        return json.loads(METRICS.read_text())
    return {"detail": "Model not trained yet. Run `python -m ml.train`."}


@router.post("/ml/score")
def ml_score(body: ScoreRequest, _: User = Depends(require_role("officer"))):
    return service.detector().score(body.history)
