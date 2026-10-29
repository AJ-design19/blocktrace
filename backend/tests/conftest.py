import os
import tempfile

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["SECRET_KEY"] = "test-secret-key-test-secret-key-123456"
os.environ["RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["LOGIN_RATE_LIMIT_PER_MINUTE"] = "100000"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.main import app
from app.models import User
from app.security import hash_password

PW = "correct-horse-battery"


@pytest.fixture(scope="session")
def client():
    with SessionLocal() as db:
        for n, r in (("admin", "admin"), ("auditor", "auditor"), ("officer", "officer")):
            if not db.execute(select(User).where(User.username == n)).scalar_one_or_none():
                db.add(User(username=n, password_hash=hash_password(PW), role=r))
        db.commit()
    return TestClient(app)


def login(client, user):
    r = client.post("/auth/login", data={"username": user, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def admin(client): return login(client, "admin")
@pytest.fixture(scope="session")
def auditor(client): return login(client, "auditor")
@pytest.fixture(scope="session")
def officer(client): return login(client, "officer")
