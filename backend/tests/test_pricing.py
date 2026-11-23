from datetime import date
from decimal import Decimal

from app.models import Role
from app.services.pricing import gst_rate_on
from tests.test_masters import make_product


def set_rate(client, product_id, rate, on, party_id=None):
    body = {"effective_from": on, "items": [{"product_id": product_id, "rate": rate}]}
    if party_id:
        body["party_id"] = party_id
    r = client.post("/api/prices", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def quote(client, product_id, on, party_id=None):
    params = {"product_id": product_id, "on": on}
    if party_id:
        params["party_id"] = party_id
    return client.get("/api/prices/quote", params=params)


def test_gst_rate_follows_effective_date(db):
    assert gst_rate_on(db, "2523", date(2025, 9, 21)) == Decimal("28.00")
    assert gst_rate_on(db, "2523", date(2025, 9, 22)) == Decimal("18.00")
    assert gst_rate_on(db, "2523", date(2017, 6, 30)) is None


def test_rate_in_force_on_a_date(client, login):
    login()
    p = make_product(client)
    set_rate(client, p["id"], "380", "2026-11-01")
    set_rate(client, p["id"], "395", "2026-11-10")

    assert quote(client, p["id"], "2026-10-31").status_code == 404
    assert quote(client, p["id"], "2026-11-05").json()["rate"] == "380.00"
    q = quote(client, p["id"], "2026-11-10").json()
    assert q["rate"] == "395.00"
    assert q["source"] == "list"
    assert q["gst_rate"] == "18.00"


def test_party_special_rate_wins_then_falls_back(client, login):
    login()
    p = make_product(client)
    party = client.post("/api/parties", json={"name": "Big Builder"}).json()["id"]
    other = client.post("/api/parties", json={"name": "Someone Else"}).json()["id"]
    set_rate(client, p["id"], "390", "2026-11-01")
    set_rate(client, p["id"], "370", "2026-11-01", party_id=party)

    special = quote(client, p["id"], "2026-11-02", party).json()
    assert (special["rate"], special["source"]) == ("370.00", "party")
    assert quote(client, p["id"], "2026-11-02", other).json()["rate"] == "390.00"


def test_setting_same_day_again_corrects_instead_of_duplicating(client, login):
    login()
    p = make_product(client)
    first = set_rate(client, p["id"], "380", "2026-11-01")[0]
    second = set_rate(client, p["id"], "385", "2026-11-01")[0]
    assert first["id"] == second["id"]
    history = client.get("/api/prices/history", params={"product_id": p["id"]}).json()
    assert [h["rate"] for h in history] == ["385.00"]


def test_rate_card_shows_current_and_previous(client, login):
    login()
    p = make_product(client)
    set_rate(client, p["id"], "380", "2026-11-01")
    set_rate(client, p["id"], "395", "2026-11-10")
    card = client.get("/api/prices/card", params={"on": "2026-11-15"}).json()
    row = next(r for r in card if r["product_id"] == p["id"])
    assert (row["rate"], row["previous_rate"], row["gst_rate"]) == ("395.00", "380.00", "18.00")


def test_only_owner_sets_prices(client, login, make_user):
    login()
    p = make_product(client)
    client.post("/api/auth/logout")
    login("clerk", Role.BILLING)
    body = {"items": [{"product_id": p["id"], "rate": "100"}]}
    assert client.post("/api/prices", json=body).status_code == 403


def test_rejects_unknown_product_and_non_positive_rate(client, login):
    login()
    p = make_product(client)
    unknown = {"items": [{"product_id": 999999, "rate": "1"}]}
    zero = {"items": [{"product_id": p["id"], "rate": "0"}]}
    assert client.post("/api/prices", json=unknown).status_code == 404
    assert client.post("/api/prices", json=zero).status_code == 422
