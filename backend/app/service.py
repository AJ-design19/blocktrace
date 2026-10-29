"""Business logic. The single place where a transaction is validated, scored,
hash-linked and persisted - used by the API and the seeder alike."""
from __future__ import annotations

import json
import threading
import time
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ml.detector import Detector

from . import ledger, rules
from .config import get_settings
from .models import Account, Alert, AuditLog, Transaction

settings = get_settings()
_write_lock = threading.Lock()   # serialises hash-chain appends within a process
_detector: Detector | None = None


def detector() -> Detector:
    global _detector
    if _detector is None:
        _detector = Detector()
    return _detector


def audit(db: Session, actor: str, action: str, target: str = "", detail: str = "") -> None:
    last = db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(1)).scalar_one_or_none()
    prev = last.hash if last else ledger.GENESIS
    ts = int(time.time())
    h = ledger.sha256(f"{prev}|{actor}|{action}|{target}|{detail}|{ts}")
    db.add(AuditLog(actor=actor, action=action, target=target, detail=detail, ts=ts, prev_hash=prev, hash=h))


def level_for(score: float) -> str:
    if score >= settings.risk_high_threshold:
        return "high"
    if score >= settings.risk_alert_threshold:
        return "medium"
    return "low"


def to_out(t: Transaction) -> dict:
    return {"token": t.token, "parent_token": t.parent_token, "sender": t.sender, "receiver": t.receiver,
            "amount": t.amount_paise / 100, "remaining": t.remaining_paise / 100, "purpose": t.purpose,
            "ts": t.ts, "status": t.status, "risk_score": t.risk_score, "risk_level": t.risk_level,
            "risk_reasons": json.loads(t.risk_reasons), "tx_hash": t.tx_hash, "batch_id": t.batch_id}


def create_transaction(db: Session, sender: str, receiver: str, amount: Decimal, purpose: str,
                       parent_token: str | None, actor: str, ts: int | None = None) -> Transaction:
    amount_paise = int((amount * 100).to_integral_value())
    ts = ts or int(time.time())

    with _write_lock:
        if db.bind.dialect.name == "postgresql":      # cross-process lock in production
            db.execute(text("SELECT pg_advisory_xact_lock(7243001)"))

        accounts = set(db.execute(select(Account.id).where(Account.id.in_([sender, receiver]))).scalars())
        if sender not in accounts or receiver not in accounts:
            raise HTTPException(404, "Unknown sender or receiver account")

        parent = None
        if parent_token:
            parent = db.execute(select(Transaction).where(Transaction.token == parent_token).with_for_update()).scalar_one_or_none() \
                if db.bind.dialect.name != "sqlite" else \
                db.execute(select(Transaction).where(Transaction.token == parent_token)).scalar_one_or_none()
            if not parent:
                raise HTTPException(404, "Parent token not found")
            if parent.receiver != sender:
                raise HTTPException(403, "Only the current holder of a token can forward it")
            if parent.status == "frozen":
                raise HTTPException(423, "Parent token is frozen pending investigation")
            if amount_paise > parent.remaining_paise:
                raise HTTPException(422, f"Amount exceeds remaining balance of parent token ({parent.remaining_paise / 100:.2f})")

        # --- scoring: LSTM over the sender's recent sequence + deterministic rules
        hist_rows = db.execute(select(Transaction).where(Transaction.sender == sender, Transaction.ts <= ts)
                               .order_by(Transaction.ts.desc(), Transaction.id.desc()).limit(9)).scalars().all()[::-1]
        history = [{"ts": r.ts, "amount": r.amount_paise / 100, "counterparty": r.receiver} for r in hist_rows]
        history.append({"ts": ts, "amount": amount_paise / 100, "counterparty": receiver})
        ml = detector().score(history)
        rule_score, rule_reasons = rules.evaluate(db, sender, receiver, amount_paise, ts, parent)
        combined = 1 - (1 - ml["score"]) * (1 - rule_score)          # noisy-OR: either signal can raise the alarm
        level = level_for(combined)
        reasons = ml["reasons"] + rule_reasons

        # --- ledger: token + hash chain
        payload = ledger.canonical(sender, receiver, amount_paise, parent_token, purpose, ts)
        token = ledger.new_token(payload)
        last = db.execute(select(Transaction).order_by(Transaction.id.desc()).limit(1)).scalar_one_or_none()
        prev = last.tx_hash if last else ledger.GENESIS
        tx = Transaction(token=token, parent_token=parent_token, sender=sender, receiver=receiver,
                         amount_paise=amount_paise, remaining_paise=amount_paise, purpose=purpose, ts=ts,
                         prev_hash=prev, tx_hash=ledger.link_hash(prev, token, payload),
                         status="flagged" if level == "high" else "active",
                         risk_score=round(combined, 4), risk_level=level,
                         risk_reasons=json.dumps(reasons), created_by=actor)
        if parent:
            parent.remaining_paise -= amount_paise
        db.add(tx)
        db.flush()
        if level != "low":
            db.add(Alert(token=token, level=level, score=tx.risk_score, reasons=json.dumps(reasons)))
        audit(db, actor, "tx.create", token, f"{sender}->{receiver} {amount_paise / 100:.2f} risk={level}")
        db.commit()
        return tx


def verify_chain(db: Session) -> dict:
    """Recompute every link. Any edited row breaks the chain at a precise position."""
    prev, count = ledger.GENESIS, 0
    for t in db.execute(select(Transaction).order_by(Transaction.id)).scalars():
        payload = ledger.canonical(t.sender, t.receiver, t.amount_paise, t.parent_token, t.purpose, t.ts)
        if t.prev_hash != prev or t.tx_hash != ledger.link_hash(prev, t.token, payload):
            return {"valid": False, "checked": count, "broken_at_token": t.token, "broken_at_id": t.id}
        prev, count = t.tx_hash, count + 1
    return {"valid": True, "checked": count, "head": prev}


def trace(db: Session, token: str) -> dict:
    root = db.execute(select(Transaction).where(Transaction.token == token)).scalar_one_or_none()
    if not root:
        raise HTTPException(404, "Token not found")
    ancestors, cur = [], root
    while cur.parent_token and len(ancestors) < 64:
        cur = db.execute(select(Transaction).where(Transaction.token == cur.parent_token)).scalar_one()
        ancestors.append(cur)
    origin = ancestors[-1] if ancestors else root

    nodes, edges, frontier, depth = {origin.token: (origin, 0)}, [], [origin], 0
    while frontier and depth < 32:
        depth += 1
        kids = db.execute(select(Transaction).where(Transaction.parent_token.in_([f.token for f in frontier]))).scalars().all()
        for k in kids:
            nodes[k.token] = (k, depth)
            edges.append({"from": k.parent_token, "to": k.token})
        frontier = kids
    leaves = [n for n, _ in nodes.values() if not any(e["from"] == n.token for e in edges)]
    return {
        "focus": token,
        "origin": to_out(origin),
        "nodes": [{**to_out(n), "depth": d} for n, d in sorted(nodes.values(), key=lambda x: (x[1], x[0].ts))],
        "edges": edges,
        "summary": {
            "hops": max((d for _, d in nodes.values()), default=0),
            "origin_amount": origin.amount_paise / 100,
            "still_unspent": sum(n.remaining_paise for n, _ in nodes.values()) / 100,
            "final_recipients": sorted({n.receiver for n in leaves}),
            "flagged_nodes": sum(1 for n, _ in nodes.values() if n.risk_level != "low"),
        },
    }


def anchor_pending(db: Session, actor: str, chain_anchor) -> dict | None:
    from .models import Batch
    pending = db.execute(select(Transaction).where(Transaction.batch_id.is_(None)).order_by(Transaction.id)
                         .limit(settings.anchor_batch_size)).scalars().all()
    if not pending:
        return None
    root = ledger.merkle_root([t.tx_hash for t in pending])
    batch = Batch(merkle_root=root, leaf_count=len(pending), chain_tx=chain_anchor(root, len(pending)))
    db.add(batch)
    db.flush()
    for t in pending:
        t.batch_id = batch.id
    audit(db, actor, "ledger.anchor", root, f"{len(pending)} txs")
    db.commit()
    return {"batch_id": batch.id, "merkle_root": root, "leaf_count": len(pending), "chain_tx": batch.chain_tx}
