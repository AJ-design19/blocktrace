import itertools

from app import ledger

_n = itertools.count()


def mk_accounts(client, h, *ids):
    for i in ids:
        client.post("/accounts", json={"id": i, "name": i.title(), "kind": "contractor"}, headers=h)


def tx(client, h, s, r, amt, parent=None, purpose="work"):
    return client.post("/transactions", json={"sender": s, "receiver": r, "amount": str(amt), "purpose": purpose, "parent_token": parent}, headers=h)


def test_auth_required_and_login_failure(client):
    assert client.get("/transactions").status_code == 401
    assert client.post("/auth/login", data={"username": "admin", "password": "wrong-password"}).status_code == 401


def test_roles_enforced(client, officer, auditor):
    assert client.get("/alerts", headers=officer).status_code == 403
    assert client.get("/alerts", headers=auditor).status_code == 200
    assert client.post("/ledger/anchor", headers=auditor).status_code == 403


def test_unique_tokens_and_traceability(client, officer):
    mk_accounts(client, officer, "t-dept", "t-a", "t-b", "t-c")
    root = tx(client, officer, "t-dept", "t-a", 1000000).json()
    c1 = tx(client, officer, "t-a", "t-b", 300000, root["token"]).json()
    c2 = tx(client, officer, "t-b", "t-c", 100000, c1["token"]).json()
    assert len({root["token"], c1["token"], c2["token"]}) == 3 and len(root["token"]) == 64
    t = client.get(f"/transactions/{c2['token']}/trace", headers=officer).json()
    assert t["origin"]["token"] == root["token"]
    assert t["summary"]["hops"] == 2
    assert "t-c" in t["summary"]["final_recipients"]


def test_cannot_overspend_or_forward_unowned(client, officer):
    mk_accounts(client, officer, "o-dept", "o-a", "o-b")
    root = tx(client, officer, "o-dept", "o-a", 1000).json()
    assert tx(client, officer, "o-a", "o-b", 1001, root["token"]).status_code == 422
    assert tx(client, officer, "o-b", "o-a", 10, root["token"]).status_code == 403
    assert tx(client, officer, "o-a", "o-b", 1000, root["token"]).status_code == 201
    assert tx(client, officer, "o-a", "o-b", 1, root["token"]).status_code == 422   # nothing left


def test_structuring_is_flagged(client, officer, auditor):
    mk_accounts(client, officer, "s-a", "s-x")
    last = None
    for i in range(3):
        last = tx(client, officer, "s-a", "s-x", 49500 - i * 10).json()
    assert last["risk_level"] != "low"
    assert any("Structuring" in r for r in last["risk_reasons"])
    assert any(a["token"] == last["token"] for a in client.get("/alerts", headers=auditor).json())


def test_circular_flow_detected(client, officer):
    mk_accounts(client, officer, "c-a", "c-b")
    tx(client, officer, "c-a", "c-b", 10000)
    back = tx(client, officer, "c-b", "c-a", 9000).json()
    assert any("Circular" in r for r in back["risk_reasons"])


def test_freeze_blocks_forwarding(client, officer, auditor):
    mk_accounts(client, officer, "f-d", "f-a", "f-b")
    root = tx(client, officer, "f-d", "f-a", 500).json()
    # create alert path: flag account then send
    client.post("/accounts/f-a/flag", headers=auditor)
    child = tx(client, officer, "f-a", "f-b", 100, root["token"]).json()
    alert = next(a for a in client.get("/alerts", headers=auditor).json() if a["token"] == child["token"])
    r = client.patch(f"/alerts/{alert['id']}", json={"status": "investigating", "freeze": True, "note": "hold"}, headers=auditor)
    assert r.status_code == 200
    assert client.get(f"/transactions/{child['token']}", headers=auditor).json()["status"] == "frozen"
    assert tx(client, officer, "f-b", "f-d", 10, child["token"]).status_code == 423


def test_ledger_valid_then_tamper_detected(client, officer, admin):
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models import Transaction
    assert client.get("/ledger/verify").json()["valid"] is True
    with SessionLocal() as db:
        victim = db.execute(select(Transaction).order_by(Transaction.id).offset(2).limit(1)).scalar_one()
        original, tok = victim.amount_paise, victim.token
        victim.amount_paise += 1
        db.commit()
    res = client.get("/ledger/verify").json()
    assert res["valid"] is False and res["broken_at_token"] == tok
    with SessionLocal() as db:
        db.execute(select(Transaction).where(Transaction.token == tok)).scalar_one().amount_paise = original
        db.commit()
    assert client.get("/ledger/verify").json()["valid"] is True


def test_anchor_and_merkle_proof(client, admin, officer):
    mk_accounts(client, officer, "m-a", "m-b")
    t = tx(client, officer, "m-a", "m-b", 123).json()
    assert client.post("/ledger/anchor", headers=admin).status_code == 200
    p = client.get(f"/transactions/{t['token']}/proof").json()
    assert p["anchored"] and p["valid"]


def test_public_verify_hides_nothing_sensitive(client, officer):
    mk_accounts(client, officer, "p-a", "p-b")
    t = tx(client, officer, "p-a", "p-b", 50).json()
    r = client.get(f"/public/verify/{t['token']}")
    assert r.status_code == 200 and r.json()["ledger_valid"] is True
    assert "risk_reasons" not in r.json()


def test_validation(client, officer):
    assert client.post("/transactions", json={"sender": "a", "receiver": "a", "amount": "5"}, headers=officer).status_code == 422
    assert client.post("/transactions", json={"sender": "a", "receiver": "b", "amount": "-5"}, headers=officer).status_code == 422


def test_csv_export_neutralises_formulas(client, officer, auditor):
    mk_accounts(client, officer, "e-a", "e-b")
    tx(client, officer, "e-a", "e-b", 5, purpose="=HYPERLINK(\"http://evil\")")
    body = client.get("/transactions/export.csv", headers=auditor).text
    assert "'=HYPERLINK" in body


def test_merkle_unit():
    leaves = [ledger.sha256(str(i)) for i in range(7)]
    root = ledger.merkle_root(leaves)
    for i, leaf in enumerate(leaves):
        assert ledger.verify_proof(leaf, ledger.merkle_proof(leaves, i), root)
    assert not ledger.verify_proof(ledger.sha256("x"), ledger.merkle_proof(leaves, 0), root)
