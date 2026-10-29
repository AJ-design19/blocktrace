import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import ledger, schemas, service
from ..database import get_db
from ..models import Batch, Transaction, User
from ..security import current_user, require_role

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("", response_model=schemas.TransactionOut, status_code=201)
def create(body: schemas.TransactionCreate, db: Session = Depends(get_db), user: User = Depends(require_role("officer"))):
    tx = service.create_transaction(db, body.sender, body.receiver, body.amount, body.purpose, body.parent_token, user.username)
    return service.to_out(tx)


@router.get("", response_model=list[schemas.TransactionOut])
def list_transactions(
    account: str | None = None, risk: str | None = Query(None, pattern="^(low|medium|high)$"),
    status: str | None = None, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), _: User = Depends(current_user),
):
    q = select(Transaction).order_by(Transaction.id.desc()).limit(limit).offset(offset)
    if account:
        q = q.where(or_(Transaction.sender == account, Transaction.receiver == account))
    if risk:
        q = q.where(Transaction.risk_level == risk)
    if status:
        q = q.where(Transaction.status == status)
    return [service.to_out(t) for t in db.execute(q).scalars()]


@router.get("/export.csv")
def export_csv(db: Session = Depends(get_db), _: User = Depends(require_role("auditor"))):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["token", "parent_token", "sender", "receiver", "amount", "purpose", "ts", "status", "risk_score", "risk_level", "tx_hash"])
    for t in db.execute(select(Transaction).order_by(Transaction.id)).scalars():
        # prefix with ' to neutralise spreadsheet formula injection from free-text fields
        safe = lambda s: ("'" + s) if s[:1] in "=+-@" else s
        w.writerow([t.token, t.parent_token or "", t.sender, t.receiver, f"{t.amount_paise / 100:.2f}", safe(t.purpose),
                    t.ts, t.status, t.risk_score, t.risk_level, t.tx_hash])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=blocktrace_ledger.csv"})


@router.get("/{token}", response_model=schemas.TransactionOut)
def get_one(token: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    t = db.execute(select(Transaction).where(Transaction.token == token)).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Token not found")
    return service.to_out(t)


@router.get("/{token}/trace")
def trace(token: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return service.trace(db, token)


@router.get("/{token}/proof")
def proof(token: str, db: Session = Depends(get_db)):
    """Merkle inclusion proof - anyone can check a token was part of an anchored batch."""
    t = db.execute(select(Transaction).where(Transaction.token == token)).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Token not found")
    if t.batch_id is None:
        return {"token": token, "anchored": False}
    batch = db.get(Batch, t.batch_id)
    leaves = [h for h in db.execute(select(Transaction.tx_hash).where(Transaction.batch_id == t.batch_id).order_by(Transaction.id)).scalars()]
    idx = leaves.index(t.tx_hash)
    p = ledger.merkle_proof(leaves, idx)
    return {"token": token, "anchored": True, "batch_id": batch.id, "merkle_root": batch.merkle_root,
            "chain_tx": batch.chain_tx, "leaf": t.tx_hash, "proof": p, "valid": ledger.verify_proof(t.tx_hash, p, batch.merkle_root)}
