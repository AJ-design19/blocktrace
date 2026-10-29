from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import chain, service
from ..database import get_db
from ..models import Alert, AuditLog, Batch, Transaction, User
from ..security import current_user, require_role

router = APIRouter(tags=["ledger"])


@router.get("/ledger/verify")
def verify(db: Session = Depends(get_db)):
    """Public: anyone can re-verify the entire hash chain."""
    return service.verify_chain(db)


@router.post("/ledger/anchor")
def anchor(db: Session = Depends(get_db), user: User = Depends(require_role("admin"))):
    res = service.anchor_pending(db, user.username, chain.anchor)
    if not res:
        raise HTTPException(409, "Nothing to anchor")
    return res


@router.get("/ledger/batches")
def batches(db: Session = Depends(get_db)):
    return [{"id": b.id, "merkle_root": b.merkle_root, "leaf_count": b.leaf_count, "chain_tx": b.chain_tx,
             "created_at": b.created_at} for b in db.execute(select(Batch).order_by(Batch.id.desc()).limit(50)).scalars()]


@router.get("/audit-log")
def audit_log(limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_role("auditor"))):
    rows = db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 500))).scalars()
    return [{"id": r.id, "actor": r.actor, "action": r.action, "target": r.target, "detail": r.detail, "ts": r.ts, "hash": r.hash} for r in rows]


@router.get("/stats")
def stats(db: Session = Depends(get_db), _: User = Depends(current_user)):
    total, volume = db.execute(select(func.count(Transaction.id), func.coalesce(func.sum(Transaction.amount_paise), 0))).one()
    by_level = dict(db.execute(select(Transaction.risk_level, func.count()).group_by(Transaction.risk_level)).all())
    open_alerts = db.execute(select(func.count(Alert.id)).where(Alert.status.in_(["open", "investigating"]))).scalar_one()
    frozen = db.execute(select(func.count(Transaction.id)).where(Transaction.status == "frozen")).scalar_one()
    since = int((datetime.now(timezone.utc) - timedelta(days=14)).timestamp())
    rows = db.execute(select(Transaction.ts, Transaction.amount_paise, Transaction.risk_level).where(Transaction.ts >= since)).all()
    daily: dict[str, dict] = {}
    for ts, amt, lvl in rows:
        d = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
        e = daily.setdefault(d, {"date": d, "volume": 0.0, "count": 0, "risky": 0})
        e["volume"] += amt / 100
        e["count"] += 1
        e["risky"] += 1 if lvl != "low" else 0
    top = db.execute(select(Transaction.sender, func.count(), func.avg(Transaction.risk_score)).where(Transaction.risk_level != "low")
                     .group_by(Transaction.sender).order_by(func.count().desc()).limit(5)).all()
    return {"transactions": total, "volume": volume / 100, "by_risk": {"low": by_level.get("low", 0), "medium": by_level.get("medium", 0), "high": by_level.get("high", 0)},
            "open_alerts": open_alerts, "frozen": frozen, "daily": [daily[k] for k in sorted(daily)],
            "top_risky_accounts": [{"account": a, "flagged_txs": c, "avg_risk": round(float(r), 3)} for a, c, r in top],
            "ledger": service.verify_chain(db)}
