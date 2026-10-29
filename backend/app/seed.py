"""Create the admin user and a demo scenario.   python -m app.seed
Set ADMIN_PASSWORD in the environment; there is no default password."""
import os
import sys
import time
from decimal import Decimal

from sqlalchemy import select

from .database import SessionLocal, engine
from .models import Account, Base, User
from .security import hash_password
from . import service


def main(demo: bool = True):
    Base.metadata.create_all(engine)
    pw = os.getenv("ADMIN_PASSWORD")
    if not pw or len(pw) < 10:
        sys.exit("Set ADMIN_PASSWORD (min 10 chars) before seeding.")
    with SessionLocal() as db:
        for name, role in (("admin", "admin"), ("auditor", "auditor"), ("officer", "officer")):
            if not db.execute(select(User).where(User.username == name)).scalar_one_or_none():
                db.add(User(username=name, password_hash=hash_password(pw), role=role))
        db.commit()
        if not demo or db.execute(select(Account)).first():
            return
        accts = [("DEPT-ROADS", "Public Works Dept", "department"), ("CONT-ALPHA", "Alpha Constructions", "contractor"),
                 ("CONT-BETA", "Beta Materials Ltd", "contractor"), ("SUB-GAMMA", "Gamma Labour Co", "contractor"),
                 ("SUB-DELTA", "Delta Traders", "contractor"), ("BEN-WORKERS", "Site Workers Fund", "beneficiary"),
                 ("SHELL-X", "X Holdings (new)", "contractor")]
        db.add_all([Account(id=i, name=n, kind=k) for i, n, k in accts])
        db.commit()
        t0 = int(time.time()) - 3 * 86_400
        D = Decimal
        root = service.create_transaction(db, "DEPT-ROADS", "CONT-ALPHA", D("2500000"), "NH-58 resurfacing release", None, "seed", t0)
        a = service.create_transaction(db, "CONT-ALPHA", "CONT-BETA", D("600000"), "Bitumen supply", root.token, "seed", t0 + 4 * 3600)
        b = service.create_transaction(db, "CONT-ALPHA", "SUB-GAMMA", D("500000"), "Labour contract", root.token, "seed", t0 + 9 * 3600)
        service.create_transaction(db, "SUB-GAMMA", "BEN-WORKERS", D("420000"), "Worker wages", b.token, "seed", t0 + 20 * 3600)
        service.create_transaction(db, "CONT-BETA", "SUB-DELTA", D("590000"), "Sub-supply", a.token, "seed", t0 + 4 * 3600 + 900)  # rapid pass-through
        # structuring pattern from CONT-ALPHA
        for i in range(4):
            service.create_transaction(db, "CONT-ALPHA", "SHELL-X", D("49500") - D(i * 50), "Consulting", root.token, "seed", t0 + 30 * 3600 + i * 600)
        # round-trip: money heads back to the department's contractor
        service.create_transaction(db, "SUB-DELTA", "CONT-ALPHA", D("500000"), "Refund", None, "seed", t0 + 40 * 3600)
        service.anchor_pending(db, "seed", lambda r, n: None)
        print("Seeded. Log in as admin / auditor / officer with ADMIN_PASSWORD.")


if __name__ == "__main__":
    main()
