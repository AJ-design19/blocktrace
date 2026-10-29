from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas, service
from ..database import get_db
from ..models import User
from ..security import create_access_token, current_user, hash_password, require_role, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.username == form.username)).scalar_one_or_none()
    # same error + same work for unknown user and wrong password (no user enumeration)
    ok = verify_password(form.password, user.password_hash if user else "$2b$12$" + "x" * 53)
    if not user or not ok or not user.is_active:
        service.audit(db, form.username[:64], "auth.fail")
        db.commit()
        raise HTTPException(401, "Incorrect username or password")
    service.audit(db, user.username, "auth.login")
    db.commit()
    return {"access_token": create_access_token(user.username, user.role), "role": user.role}


@router.get("/me", response_model=schemas.UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.post("/users", response_model=schemas.UserOut, status_code=201)
def create_user(body: schemas.UserCreate, db: Session = Depends(get_db), admin: User = Depends(require_role("admin"))):
    if db.execute(select(User).where(User.username == body.username)).scalar_one_or_none():
        raise HTTPException(409, "Username already exists")
    user = User(username=body.username, password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    service.audit(db, admin.username, "user.create", body.username, body.role)
    db.commit()
    return user
