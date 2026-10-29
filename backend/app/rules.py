"""Deterministic rule engine. Runs next to the LSTM: rules catch known typologies
with certainty, the LSTM catches the patterns nobody wrote a rule for."""
from __future__ import annotations

from collections import deque

from sqlalchemy import select
from sqlalchemy.orm import Session

from ml.features import REPORTING_THRESHOLD

from .models import Account, Transaction

DAY = 86_400


def _has_path(db: Session, start: str, goal: str, since: int, max_depth: int = 6) -> bool:
    """Is there already a money path start -> ... -> goal? (a new goal->start edge closes a cycle)"""
    q, seen = deque([(start, 0)]), {start}
    while q:
        node, depth = q.popleft()
        if node == goal:
            return True
        if depth >= max_depth:
            continue
        rows = db.execute(select(Transaction.receiver).where(Transaction.sender == node, Transaction.ts >= since)).scalars()
        for nxt in rows:
            if nxt not in seen:
                seen.add(nxt)
                q.append((nxt, depth + 1))
    return False


def evaluate(db: Session, sender: str, receiver: str, amount_paise: int, ts: int, parent: Transaction | None) -> tuple[float, list[str]]:
    score, reasons = 0.0, []
    amount = amount_paise / 100

    # 1. structuring: repeated amounts hugging the reporting threshold
    if 0.90 * REPORTING_THRESHOLD <= amount < REPORTING_THRESHOLD:
        near = db.execute(
            select(Transaction).where(Transaction.sender == sender, Transaction.ts >= ts - DAY,
                                      Transaction.amount_paise >= int(0.90 * REPORTING_THRESHOLD * 100),
                                      Transaction.amount_paise < int(REPORTING_THRESHOLD * 100))
        ).scalars().all()
        if len(near) >= 2:
            score = max(score, 0.85)
            reasons.append(f"Structuring: {len(near) + 1} payments just under the {int(REPORTING_THRESHOLD):,} limit in 24h")

    # 2. rapid pass-through: received funds and forwards almost all of it within the hour
    if parent is not None:
        ratio = amount_paise / max(parent.amount_paise, 1)
        if ratio >= 0.95 and ts - parent.ts <= 3600:
            score = max(score, 0.60)
            reasons.append("Rapid pass-through: ≥95% of received funds forwarded within one hour")

    # 3. circular flow: receiver already (indirectly) paid the sender
    since = ts - 30 * DAY
    if sender != receiver and _has_path(db, receiver, sender, since):
        score = max(score, 0.80)
        reasons.append("Circular flow: money is returning to an earlier sender")

    # 4. velocity
    recent = db.execute(select(Transaction.id).where(Transaction.sender == sender, Transaction.ts >= ts - 3600)).scalars().all()
    if len(recent) >= 10:
        score = max(score, 0.55)
        reasons.append(f"High velocity: {len(recent) + 1} payments from one account in an hour")

    # 5. previously flagged counterparties
    flagged = db.execute(select(Account.id).where(Account.id.in_([sender, receiver]), Account.flagged.is_(True))).scalars().all()
    if flagged:
        score = max(score, 0.75)
        reasons.append(f"Involves flagged account: {', '.join(flagged)}")

    return score, reasons
