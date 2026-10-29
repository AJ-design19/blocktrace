from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas, service
from ..database import get_db
from ..models import Account, User
from ..security import current_user, require_role

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[schemas.AccountOut])
def list_accounts(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return db.execute(select(Account).order_by(Account.id)).scalars().all()


@router.post("", response_model=schemas.AccountOut, status_code=201)
def create_account(body: schemas.AccountCreate, db: Session = Depends(get_db), user: User = Depends(require_role("officer"))):
    if db.get(Account, body.id):
        raise HTTPException(409, "Account id already exists")
    acc = Account(id=body.id, name=body.name, kind=body.kind)
    db.add(acc)
    service.audit(db, user.username, "account.create", body.id)
    db.commit()
    return acc


@router.post("/{account_id}/flag", response_model=schemas.AccountOut)
def flag_account(account_id: str, flagged: bool = True, db: Session = Depends(get_db), user: User = Depends(require_role("auditor"))):
    acc = db.get(Account, account_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    acc.flagged = flagged
    service.audit(db, user.username, "account.flag" if flagged else "account.unflag", account_id)
    db.commit()
    return acc
