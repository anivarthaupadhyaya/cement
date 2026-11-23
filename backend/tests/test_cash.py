import uuid
from datetime import date, timedelta

import pytest

from app.models import Role
from tests.conftest import PASSWORD

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)


def ref() -> str:
    return uuid.uuid4().hex


@pytest.fixture
def shop(client, login):
    login()
    brand = client.post("/api/brands", json={"name": "Dalmia"}).json()["id"]
    psc = client.post("/api/products", json={"brand_id": brand, "grade": "PSC"}).json()["id"]
    client.post(
        "/api/stock/opening",
        json={
            "godown_id": 1,
            "on": "2025-01-01",
            "items": [{"product_id": psc, "qty": 1000, "unit_cost": "300"}],
        },
    )
    party = client.post("/api/parties", json={"name": "Rao", "credit_limit": "100000"}).json()["id"]
    return {"psc": psc, "party": party}


def cash_bill(client, s, qty=10, on=None):
    body = {
        "client_ref": ref(),
        "payment_mode": "cash",
        "lines": [{"product_id": s["psc"], "qty": qty, "rate": "370"}],
    }
    if on:
        body["invoice_date"] = on.isoformat()
    return client.post("/api/sales", json=body)


def expense(client, amount, category="hamali", mode="cash", on=None):
    body = {"category": category, "amount": amount, "mode": mode}
    if on:
        body["expense_date"] = on.isoformat()
    return client.post("/api/expenses", json=body)


def day(client, on=TODAY):
    return client.get("/api/cash/day", params={"on": on.isoformat()}).json()


def test_day_summary_counts_every_cash_flow(client, shop):
    bill = cash_bill(client, shop).json()  # +3700
    client.post(
        "/api/receipts",
        json={"client_ref": ref(), "party_id": shop["party"], "amount": "1000", "mode": "cash"},
    )  # +1000
    client.post(
        "/api/receipts",
        json={"client_ref": ref(), "party_id": shop["party"], "amount": "5000", "mode": "upi"},
    )  # not cash
    expense(client, "300")  # -300
    expense(client, "2000", "bank_deposit")  # -2000
    expense(client, "999", mode="upi")  # not cash
    client.post(
        f"/api/sales/{bill['id']}/returns",
        json={"reason": "burst", "items": [{"sales_line_id": bill["lines"][0]["id"], "qty": 1}]},
    )  # -370

    d = day(client)
    assert (d["cash_sales"], d["cash_receipts"], d["cash_in"]) == ("3700.00", "1000.00", "4700.00")
    assert d["expenses"] == {"hamali": "300.00", "bank_deposit": "2000.00"}
    assert d["return_refunds"] == "370.00"
    assert d["cash_out"] == "2670.00"
    assert d["opening_known"] is False


def test_close_day_then_lock_and_carry_forward(client, shop):
    cash_bill(client, shop, on=YESTERDAY)  # 3700 yesterday
    r = client.post("/api/cash/close", json={"on": YESTERDAY.isoformat(), "counted": "4700"})
    assert r.status_code == 409 and "First closing" in r.json()["detail"]

    r = client.post(
        "/api/cash/close",
        json={
            "on": YESTERDAY.isoformat(),
            "counted": "4700",
            "opening_cash": "1000",
            "denominations": {"500": 9, "100": 2},
        },
    )
    assert r.status_code == 201, r.text
    assert (r.json()["expected"], r.json()["difference"]) == ("4700.00", "0.00")

    # Closed day is locked for cash entries...
    assert cash_bill(client, shop, on=YESTERDAY).status_code == 400
    assert expense(client, "50", on=YESTERDAY).status_code == 409
    assert (
        client.post(
            "/api/cash/close", json={"on": YESTERDAY.isoformat(), "counted": "1"}
        ).status_code
        == 409
    )

    # ...and today opens with what was counted
    cash_bill(client, shop)
    today = day(client)
    assert (today["opening"], today["expected"]) == ("4700.00", "8400.00")


def test_difference_needs_a_note(client, shop):
    cash_bill(client, shop)
    body = {"on": TODAY.isoformat(), "counted": "3650", "opening_cash": "0"}
    assert client.post("/api/cash/close", json=body).status_code == 409
    r = client.post("/api/cash/close", json={**body, "notes": "Rs 50 change given extra"})
    assert r.json()["difference"] == "-50.00"


def test_cancelled_cash_bill_is_refunded_on_cancel_day_not_bill_day(client, shop):
    bill = cash_bill(client, shop, on=YESTERDAY).json()
    client.post(
        "/api/cash/close",
        json={"on": YESTERDAY.isoformat(), "counted": "3700", "opening_cash": "0"},
    )
    client.post(f"/api/sales/{bill['id']}/cancel", json={"reason": "Customer returned all"})
    assert day(client, YESTERDAY)["cash_sales"] == "3700.00"  # closed history unchanged
    today = day(client)
    assert (today["cancel_refunds"], today["expected"]) == ("3700.00", "0.00")


def test_expense_roles(client, shop, make_user):
    exp = expense(client, "120").json()
    client.post("/api/auth/logout")
    make_user("clerk", Role.BILLING)
    client.post("/api/auth/login", json={"username": "clerk", "password": PASSWORD})
    assert expense(client, "80").status_code == 201  # counter can pay hamali
    assert expense(client, "80", on=YESTERDAY).status_code == 403
    assert (
        client.post(f"/api/expenses/{exp['id']}/cancel", json={"reason": "dup"}).status_code == 403
    )
    assert (
        client.post("/api/cash/close", json={"on": TODAY.isoformat(), "counted": "0"}).status_code
        == 403
    )
