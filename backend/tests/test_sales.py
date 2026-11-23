import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.models import Role
from app.services.numbering import financial_year
from tests.conftest import PASSWORD
from tests.test_masters import valid_gstin

FY = financial_year(date.today())


def ref() -> str:
    return uuid.uuid4().hex


@pytest.fixture
def shop(client, login):
    """Owner logged in; 100 bags of OPC in stock at Rs 300; a credit customer (limit 10,000)."""
    login()
    brand = client.post("/api/brands", json={"name": "UltraTech"}).json()["id"]
    opc = client.post("/api/products", json={"brand_id": brand, "grade": "OPC 53"}).json()["id"]
    client.post(
        "/api/stock/opening",
        json={
            "godown_id": 1,
            "on": "2026-04-01",
            "items": [{"product_id": opc, "qty": 100, "unit_cost": "300"}],
        },
    )
    builder = client.post(
        "/api/parties",
        json={"name": "Coastal Builders", "credit_limit": "10000", "credit_days": 30},
    ).json()["id"]
    return {"opc": opc, "builder": builder}


def bill(s, qty=10, rate="395", **over):
    body = {
        "client_ref": ref(),
        "payment_mode": "cash",
        "customer_name": "Ramesh",
        "lines": [{"product_id": s["opc"], "qty": qty, "rate": rate}],
    }
    body.update(over)
    return body


def stock_qty(client, product_id):
    return next(r["qty"] for r in client.get("/api/stock").json() if r["product_id"] == product_id)


def switch_user(client, make_user, username, role):
    client.post("/api/auth/logout")
    make_user(username, role)
    client.post("/api/auth/login", json={"username": username, "password": PASSWORD})


# ---- Preview ------------------------------------------------------------------
def test_preview_shows_totals_margin_and_saves_nothing(client, shop):
    body = bill(shop)
    del body["client_ref"]
    p = client.post("/api/sales/preview", json=body).json()
    assert (p["taxable_total"], p["cgst_total"], p["sgst_total"]) == ("3347.46", "301.27", "301.27")
    assert p["grand_total"] == "3950.00"
    assert p["lines"][0]["available"] == 100
    assert p["margin"] == "347.46"  # 3347.46 - 10 x 300
    assert p["warnings"] == []
    assert stock_qty(client, shop["opc"]) == 100
    assert client.get("/api/sales").json() == []


def test_preview_warns_about_stock(client, shop):
    body = bill(shop, qty=150)
    del body["client_ref"]
    assert "Only 100 bags" in client.post("/api/sales/preview", json=body).json()["warnings"][0]


# ---- Saving -------------------------------------------------------------------
def test_cash_sale(client, shop):
    r = client.post("/api/sales", json=bill(shop))
    assert r.status_code == 201, r.text
    inv = r.json()
    assert inv["invoice_no"] == f"INV/{FY}/0001"
    assert inv["customer_name"] == "Ramesh"
    assert inv["grand_total"] == "3950.00"
    assert inv["amount_in_words"] == "Rupees Three Thousand Nine Hundred Fifty Only"
    assert inv["lines"][0]["cost_per_bag"] == "300.0000"
    assert inv["margin"] == "347.46"
    assert stock_qty(client, shop["opc"]) == 90


def test_numbers_are_sequential_and_gap_free(client, shop):
    assert client.post("/api/sales", json=bill(shop)).json()["invoice_no"].endswith("/0001")
    # A failed save (not enough stock) must not use up a number
    assert client.post("/api/sales", json=bill(shop, qty=1000)).status_code == 409
    assert client.post("/api/sales", json=bill(shop)).json()["invoice_no"].endswith("/0002")


def test_double_submit_returns_the_same_bill(client, shop):
    body = bill(shop)
    first = client.post("/api/sales", json=body).json()
    second = client.post("/api/sales", json=body).json()
    assert first["id"] == second["id"]
    assert stock_qty(client, shop["opc"]) == 90  # taken out once


def test_interstate_customer_pays_igst(client, shop):
    tn = client.post(
        "/api/parties", json={"name": "Chennai Infra", "gstin": valid_gstin("33")}
    ).json()["id"]
    inv = client.post("/api/sales", json=bill(shop, party_id=tn)).json()
    assert inv["is_interstate"] is True
    assert (inv["cgst_total"], inv["sgst_total"], inv["igst_total"]) == ("0.00", "0.00", "602.54")
    assert inv["customer_gstin"] == valid_gstin("33")


def test_delivery_charge_is_taxed_with_the_goods(client, shop):
    inv = client.post("/api/sales", json=bill(shop, delivery_charge="236")).json()
    assert (inv["delivery_taxable"], inv["delivery_gst"]) == ("200.00", "36.00")
    assert inv["grand_total"] == "4186.00"
    assert inv["margin"] == "347.46"  # delivery isn't margin on cement


# ---- Credit control --------------------------------------------------------------
def test_credit_bill_needs_a_customer(client, shop):
    r = client.post("/api/sales", json=bill(shop, payment_mode="credit"))
    assert r.status_code == 400


def test_credit_limit(client, shop, make_user):
    ok = bill(shop, party_id=shop["builder"], payment_mode="credit")
    assert client.post("/api/sales", json=ok).status_code == 201  # 3950 of 10000

    preview = {
        k: v
        for k, v in bill(shop, qty=20, party_id=shop["builder"], payment_mode="credit").items()
        if k != "client_ref"
    }
    p = client.post("/api/sales/preview", json=preview).json()
    assert p["outstanding"] == "3950.00"
    assert p["over_limit"] is True  # 3950 + 7900 > 10000

    over = bill(shop, qty=20, party_id=shop["builder"], payment_mode="credit")
    assert client.post("/api/sales", json=over).status_code == 409  # owner, but no reason

    over["credit_override_reason"] = "Pays every Saturday, approved by owner"
    r = client.post("/api/sales", json=over)
    assert r.status_code == 201
    assert r.json()["credit_override_reason"].startswith("Pays every")

    switch_user(client, make_user, "clerk", Role.BILLING)
    again = bill(
        shop,
        qty=1,
        party_id=shop["builder"],
        payment_mode="credit",
        credit_override_reason="please",
    )
    r = client.post("/api/sales", json=again)
    assert r.status_code == 409
    assert "owner" in r.json()["detail"]


# ---- Clerk restrictions ---------------------------------------------------------
def test_clerk_rules(client, shop, make_user):
    switch_user(client, make_user, "clerk", Role.BILLING)
    below_cost = bill(shop, rate="340")  # 340 incl. GST = 288.14 before GST < cost 300
    r = client.post("/api/sales", json=below_cost)
    assert r.status_code == 400 and "below cost" in r.json()["detail"]

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    assert client.post("/api/sales", json=bill(shop, invoice_date=yesterday)).status_code == 403

    inv = client.post("/api/sales", json=bill(shop)).json()
    assert inv["margin"] is None and inv["lines"][0]["cost_per_bag"] is None  # cost hidden
    assert client.post(f"/api/sales/{inv['id']}/cancel", json={"reason": "oops"}).status_code == 403


def test_owner_can_bill_below_cost(client, shop):
    assert client.post("/api/sales", json=bill(shop, rate="340")).status_code == 201


# ---- Cancel & returns -----------------------------------------------------------
def test_cancel_puts_stock_back_and_keeps_the_number(client, shop):
    inv = client.post("/api/sales", json=bill(shop)).json()
    r = client.post(f"/api/sales/{inv['id']}/cancel", json={"reason": "Customer changed mind"})
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    assert stock_qty(client, shop["opc"]) == 100
    assert (
        client.post(f"/api/sales/{inv['id']}/cancel", json={"reason": "again"}).status_code == 400
    )
    # Next bill gets the next number; the cancelled one stays on record
    assert client.post("/api/sales", json=bill(shop)).json()["invoice_no"].endswith("/0002")
    assert client.get("/api/stock/verify").json()["ok"] is True


def test_partial_returns_add_up_exactly(client, shop):
    inv = client.post("/api/sales", json=bill(shop, qty=3)).json()  # 3 x 395 = 1185
    line = inv["lines"][0]["id"]

    r1 = client.post(
        f"/api/sales/{inv['id']}/returns",
        json={"reason": "Burst bag", "items": [{"sales_line_id": line, "qty": 1}]},
    )
    assert r1.status_code == 201, r1.text
    r2 = client.post(
        f"/api/sales/{inv['id']}/returns",
        json={"reason": "Not needed", "items": [{"sales_line_id": line, "qty": 2}]},
    )
    detail = r2.json()
    cn1, cn2 = detail["returns"]
    assert cn1["return_no"] == f"CN/{FY}/0001" and cn2["return_no"] == f"CN/{FY}/0002"
    # Credit notes together refund exactly what was billed for the goods
    from decimal import Decimal as D

    assert D(cn1["taxable_total"]) + D(cn2["taxable_total"]) == D(inv["lines"][0]["taxable"])
    assert D(cn1["cgst_total"]) + D(cn1["sgst_total"]) + D(cn2["cgst_total"]) + D(
        cn2["sgst_total"]
    ) == D(inv["lines"][0]["gst_amount"])
    assert detail["lines"][0]["qty_returned"] == 3
    assert stock_qty(client, shop["opc"]) == 100

    over = client.post(
        f"/api/sales/{inv['id']}/returns",
        json={"reason": "x" * 3, "items": [{"sales_line_id": line, "qty": 1}]},
    )
    assert over.status_code == 400


def test_return_reduces_credit_outstanding(client, shop):
    inv = client.post(
        "/api/sales", json=bill(shop, party_id=shop["builder"], payment_mode="credit")
    ).json()
    client.post(
        f"/api/sales/{inv['id']}/returns",
        json={"reason": "Damaged", "items": [{"sales_line_id": inv["lines"][0]["id"], "qty": 10}]},
    )
    preview = bill(shop, qty=1, party_id=shop["builder"], payment_mode="credit")
    del preview["client_ref"]
    assert client.post("/api/sales/preview", json=preview).json()["outstanding"] == "0.00"


def test_no_return_on_cancelled_bill(client, shop):
    inv = client.post("/api/sales", json=bill(shop)).json()
    client.post(f"/api/sales/{inv['id']}/cancel", json={"reason": "Wrong customer"})
    r = client.post(
        f"/api/sales/{inv['id']}/returns",
        json={"reason": "late", "items": [{"sales_line_id": inv["lines"][0]["id"], "qty": 1}]},
    )
    assert r.status_code == 400


def test_bills_cannot_be_deleted(client, shop, db):
    client.post("/api/sales", json=bill(shop))
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("DELETE FROM sales_invoices"))


def test_search_and_shop_details(client, shop):
    client.post("/api/sales", json=bill(shop, customer_name="Suresh Hegde"))
    assert len(client.get("/api/sales", params={"q": "hegde"}).json()) == 1
    assert len(client.get("/api/sales", params={"q": f"INV/{FY}/0001"}).json()) == 1
    assert client.get("/api/shop").json()["state_code"] == "29"
