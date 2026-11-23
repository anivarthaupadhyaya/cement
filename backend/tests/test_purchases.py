from datetime import date

import pytest

from app.models import Role
from tests.test_masters import valid_gstin


@pytest.fixture
def setup(client, login):
    """Owner logged in, one in-state supplier, two products."""
    login()
    brand = client.post("/api/brands", json={"name": "UltraTech"}).json()["id"]
    opc = client.post("/api/products", json={"brand_id": brand, "grade": "OPC 53"}).json()
    ppc = client.post("/api/products", json={"brand_id": brand, "grade": "PPC"}).json()
    supplier = client.post(
        "/api/parties", json={"name": "UltraTech CFA", "kind": "supplier", "gstin": valid_gstin()}
    ).json()
    return {"opc": opc["id"], "ppc": ppc["id"], "supplier": supplier["id"]}


def purchase_body(s, **over):
    body = {
        "supplier_id": s["supplier"],
        "supplier_invoice_no": "UT/2026/0457",
        "invoice_date": "2026-11-20",
        "godown_id": 1,
        "vehicle_no": "KA20AB1234",
        "freight": "3000",
        "unloading": "450",
        "lines": [
            {"product_id": s["opc"], "qty_invoiced": 100, "qty_damaged": 2, "rate": "300.00"},
            {"product_id": s["ppc"], "qty_invoiced": 50, "rate": "280.00"},
        ],
    }
    body.update(over)
    return body


def stock_of(client, product_id):
    rows = client.get("/api/stock").json()
    return next(r for r in rows if r["product_id"] == product_id and r["godown_id"] == 1)


def test_purchase_totals_and_landed_cost(client, setup):
    r = client.post("/api/purchases", json=purchase_body(setup))
    assert r.status_code == 201, r.text
    p = r.json()

    assert p["taxable_total"] == "44000.00"  # 100x300 + 50x280
    assert (p["cgst_total"], p["sgst_total"], p["igst_total"]) == ("3960.00", "3960.00", "0.00")
    assert p["invoice_total"] == "51920.00"
    assert p["is_interstate"] is False

    opc, ppc = p["lines"]
    # 3450 of charges split by weight 5000 kg : 2500 kg
    assert (opc["charges"], ppc["charges"]) == ("2300.00", "1150.00")
    assert (opc["qty_received"], opc["qty_damaged"], opc["qty_short"]) == (98, 2, 0)
    # (30000 + 2300) / 98 good bags
    assert opc["landed_cost"] == "329.5918"
    assert ppc["landed_cost"] == "303.0000"


def test_good_bags_go_into_stock_at_landed_cost(client, setup):
    client.post("/api/purchases", json=purchase_body(setup))
    row = stock_of(client, setup["opc"])
    assert row["qty"] == 98
    assert row["avg_cost"] == "329.5918"
    assert client.get("/api/stock/verify").json()["ok"] is True


def test_short_bags_are_recorded(client, setup):
    body = purchase_body(setup)
    body["lines"][1]["qty_received"] = 47  # 3 bags never arrived
    p = client.post("/api/purchases", json=body).json()
    assert p["lines"][1]["qty_short"] == 3
    assert stock_of(client, setup["ppc"])["qty"] == 47


def test_interstate_supplier_uses_igst(client, setup):
    other = client.post(
        "/api/parties",
        json={"name": "TN Depot", "kind": "supplier", "gstin": valid_gstin("33", "AAACT9999Q")},
    ).json()["id"]
    p = client.post("/api/purchases", json=purchase_body(setup, supplier_id=other)).json()
    assert p["is_interstate"] is True
    assert (p["cgst_total"], p["sgst_total"], p["igst_total"]) == ("0.00", "0.00", "7920.00")


def test_old_bill_uses_old_gst_rate(client, setup):
    p = client.post("/api/purchases", json=purchase_body(setup, invoice_date="2025-09-01")).json()
    assert p["lines"][0]["gst_rate"] == "28.00"


def test_same_supplier_bill_cannot_be_entered_twice(client, setup):
    assert client.post("/api/purchases", json=purchase_body(setup)).status_code == 201
    assert client.post("/api/purchases", json=purchase_body(setup)).status_code == 409


def test_validation_errors(client, setup):
    customer = client.post("/api/parties", json={"name": "A customer"}).json()["id"]
    assert (
        client.post("/api/purchases", json=purchase_body(setup, supplier_id=customer)).status_code
        == 400
    )

    future = purchase_body(setup, invoice_date=date(2099, 1, 1).isoformat())
    assert client.post("/api/purchases", json=future).status_code == 422

    too_many = purchase_body(setup)
    too_many["lines"][0].update(qty_received=99, qty_damaged=2)
    assert client.post("/api/purchases", json=too_many).status_code == 422


def test_cancel_reverses_stock_and_frees_the_bill_number(client, setup):
    pid = client.post("/api/purchases", json=purchase_body(setup)).json()["id"]
    r = client.post(f"/api/purchases/{pid}/cancel", json={"reason": "Wrong rate entered"})
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    assert stock_of(client, setup["opc"])["qty"] == 0
    assert client.post(f"/api/purchases/{pid}/cancel", json={"reason": "again"}).status_code == 400
    # The corrected bill can now be entered with the same number
    assert client.post("/api/purchases", json=purchase_body(setup)).status_code == 201
    assert client.get("/api/stock/verify").json()["ok"] is True


def test_cannot_cancel_after_bags_are_gone(client, setup):
    pid = client.post("/api/purchases", json=purchase_body(setup)).json()["id"]
    adj = {
        "product_id": setup["opc"],
        "godown_id": 1,
        "kind": "damage",
        "qty": -10,
        "reason": "Wet",
    }
    assert client.post("/api/stock/adjustments", json=adj).status_code == 201
    r = client.post(f"/api/purchases/{pid}/cancel", json={"reason": "Wrong"})
    assert r.status_code == 409
    assert stock_of(client, setup["opc"])["qty"] == 88  # nothing changed


def test_roles(client, setup, make_user):
    pid = client.post("/api/purchases", json=purchase_body(setup)).json()["id"]
    client.post("/api/auth/logout")

    make_user("keeper", Role.GODOWN)
    client.post("/api/auth/login", json={"username": "keeper", "password": "secret-pass-123"})
    assert client.get(f"/api/purchases/{pid}").status_code == 200
    assert client.post(f"/api/purchases/{pid}/cancel", json={"reason": "no"}).status_code == 403
    row = stock_of(client, setup["opc"])
    assert row["qty"] == 98 and row["avg_cost"] is None and row["value"] is None  # cost hidden

    client.post("/api/auth/logout")
    make_user("clerk", Role.BILLING)
    client.post("/api/auth/login", json={"username": "clerk", "password": "secret-pass-123"})
    assert client.get("/api/purchases").status_code == 403


def test_adjustments(client, setup):
    client.post("/api/purchases", json=purchase_body(setup))
    base = {"product_id": setup["ppc"], "godown_id": 1, "reason": "Physical count"}

    assert (
        client.post("/api/stock/adjustments", json={**base, "kind": "damage", "qty": 5}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/stock/adjustments", json={**base, "kind": "damage", "qty": -500}
        ).status_code
        == 409
    )

    found = client.post("/api/stock/adjustments", json={**base, "kind": "adjustment", "qty": 2})
    assert found.status_code == 201
    assert found.json()["unit_cost"] == "303.0000"  # valued at current average
    assert stock_of(client, setup["ppc"])["qty"] == 52

    moves = client.get("/api/stock/movements", params={"product_id": setup["ppc"]}).json()
    assert [m["kind"] for m in moves] == ["adjustment", "purchase"]


def test_opening_stock(client, setup):
    body = {
        "godown_id": 1,
        "on": "2026-11-01",
        "items": [{"product_id": setup["opc"], "qty": 200, "unit_cost": "310"}],
    }
    assert client.post("/api/stock/opening", json=body).status_code == 201
    row = stock_of(client, setup["opc"])
    assert (row["qty"], row["avg_cost"], row["value"]) == (200, "310.0000", "62000.00")
