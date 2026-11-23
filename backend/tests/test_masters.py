from sqlalchemy import select

from app.models import AuditLog, Role
from app.services.gst import gstin_checksum


def valid_gstin(state: str = "29", pan: str = "AAACU1234F") -> str:
    body = f"{state}{pan}1Z"
    return body + gstin_checksum(body)


def make_product(client, brand="UltraTech", grade="PPC"):
    brand_id = client.post("/api/brands", json={"name": brand}).json()["id"]
    r = client.post("/api/products", json={"brand_id": brand_id, "grade": grade})
    assert r.status_code == 201, r.text
    return r.json()


# ---- Brands & products ------------------------------------------------------
def test_brand_names_are_unique(client, login):
    login()
    assert client.post("/api/brands", json={"name": "ACC"}).status_code == 201
    assert client.post("/api/brands", json={"name": "ACC"}).status_code == 409


def test_billing_clerk_cannot_edit_brands(client, login):
    login("clerk", Role.BILLING)
    assert client.post("/api/brands", json={"name": "ACC"}).status_code == 403
    assert client.get("/api/brands").status_code == 200  # but can read


def test_product_defaults_and_display_name(client, login):
    login()
    p = make_product(client)
    assert p["name"] == "UltraTech PPC (50 kg)"
    assert p["hsn_code"] == "2523"
    assert p["bag_kg"] == "50.00"  # money/quantities travel as exact decimal strings


def test_duplicate_product_rejected(client, login):
    login()
    p = make_product(client)
    r = client.post("/api/products", json={"brand_id": p["brand_id"], "grade": "PPC"})
    assert r.status_code == 409


def test_deactivated_products_filtered(client, login):
    login()
    p = make_product(client)
    client.patch(f"/api/products/{p['id']}", json={"is_active": False})
    active = client.get("/api/products", params={"active": True}).json()
    assert p["id"] not in [x["id"] for x in active]


# ---- Godowns & GST ------------------------------------------------------------
def test_main_godown_seeded(client, login):
    login("clerk", Role.BILLING)
    assert "Main Godown" in [g["name"] for g in client.get("/api/godowns").json()]


def test_gst_rates_seeded_and_new_rate_for_same_day_conflicts(client, login):
    login()
    rates = client.get("/api/gst-rates").json()
    assert {(r["rate"], r["effective_from"]) for r in rates if r["hsn_code"] == "2523"} >= {
        ("28.00", "2017-07-01"),
        ("18.00", "2025-09-22"),
    }
    body = {"hsn_code": "2523", "rate": "12", "effective_from": "2025-09-22"}
    assert client.post("/api/gst-rates", json=body).status_code == 409


# ---- Parties --------------------------------------------------------------------
def test_party_state_comes_from_gstin(client, login):
    login()
    gstin = valid_gstin("33")
    r = client.post(
        "/api/parties",
        json={"name": "Chennai Builders", "gstin": gstin.lower(), "state_code": "29"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["gstin"] == gstin
    assert r.json()["state_code"] == "33"


def test_party_without_gstin_defaults_to_shop_state(client, login):
    login()
    r = client.post("/api/parties", json={"name": "Walk-in Ramesh", "phone": "9876543210"})
    assert r.json()["state_code"] == "29"


def test_invalid_gstin_rejected_with_reason(client, login):
    login()
    bad = valid_gstin()[:-1] + ("A" if valid_gstin()[-1] != "A" else "B")
    r = client.post("/api/parties", json={"name": "X", "gstin": bad})
    assert r.status_code == 422
    assert "check digit" in r.text


def test_duplicate_gstin_rejected(client, login):
    login()
    body = {"name": "A", "gstin": valid_gstin()}
    assert client.post("/api/parties", json=body).status_code == 201
    assert client.post("/api/parties", json={**body, "name": "B"}).status_code == 409


def test_clerk_can_add_cash_customer_but_not_give_credit(client, login):
    login("clerk", Role.BILLING)
    assert client.post("/api/parties", json={"name": "Cash Customer"}).status_code == 201
    r = client.post("/api/parties", json={"name": "Credit Customer", "credit_limit": "50000"})
    assert r.status_code == 403


def test_party_search_by_name_or_phone(client, login):
    login()
    client.post("/api/parties", json={"name": "Sri Lakshmi Traders", "phone": "9845012345"})
    client.post("/api/parties", json={"name": "Other", "kind": "supplier"})
    assert [p["name"] for p in client.get("/api/parties?q=lakshmi").json()] == [
        "Sri Lakshmi Traders"
    ]
    assert len(client.get("/api/parties?q=98450").json()) == 1
    assert [p["name"] for p in client.get("/api/parties?kind=supplier").json()] == ["Other"]


def test_credit_limit_change_is_audited(client, login, db):
    owner = login()
    pid = client.post("/api/parties", json={"name": "Builder"}).json()["id"]
    client.patch(f"/api/parties/{pid}", json={"credit_limit": "100000", "credit_days": 30})
    entry = db.scalars(
        select(AuditLog)
        .where(AuditLog.table_name == "parties", AuditLog.action == "UPDATE")
        .order_by(AuditLog.id.desc())
    ).first()
    assert entry is not None and entry.user_id == owner.id
    assert entry.old_data["credit_limit"] == 0
    assert entry.new_data["credit_limit"] == 100000
