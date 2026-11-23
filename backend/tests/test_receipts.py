import itertools
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.models import Role
from app.services.numbering import financial_year
from tests.conftest import PASSWORD

TODAY = date.today()
FY = financial_year(TODAY)
_names = itertools.count()


def ref() -> str:
    return uuid.uuid4().hex


def days_ago(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


@pytest.fixture
def shop(client, login):
    login()
    brand = client.post("/api/brands", json={"name": "ACC"}).json()["id"]
    opc = client.post("/api/products", json={"brand_id": brand, "grade": "OPC 53"}).json()["id"]
    client.post(
        "/api/stock/opening",
        json={
            "godown_id": 1,
            "on": "2025-01-01",
            "items": [{"product_id": opc, "qty": 100000, "unit_cost": "300"}],
        },
    )
    return {"opc": opc}


@pytest.fixture
def builder(client, shop):
    return new_customer(client)


def new_customer(client, limit="10000000", days=30):
    return client.post(
        "/api/parties",
        json={"name": f"Builder {next(_names)}", "credit_limit": limit, "credit_days": days},
    ).json()["id"]


def credit_bill(client, shop, party, qty=10, rate="395", on=None):
    body = {
        "client_ref": ref(),
        "party_id": party,
        "payment_mode": "credit",
        "lines": [{"product_id": shop["opc"], "qty": qty, "rate": rate}],
    }
    if on:
        body["invoice_date"] = on
    r = client.post("/api/sales", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def pay(client, party, amount, mode="cash", **extra):
    body = {"client_ref": ref(), "party_id": party, "amount": amount, "mode": mode, **extra}
    r = client.post("/api/receipts", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def outstanding(client, party):
    return client.post("/api/receipts/preview", json={"party_id": party, "amount": "1"}).json()[
        "outstanding"
    ]


def open_bills(client, party):
    return {
        b["ref_no"]: b["balance"] for b in client.get(f"/api/parties/{party}/open-bills").json()
    }


def ledger_ok(client):
    r = client.get("/api/reports/ledger-check").json()
    assert r["ok"], r["mismatches"]


# ---- Allocation ---------------------------------------------------------------------
def test_payment_settles_oldest_bill_first(client, shop, builder):
    a = credit_bill(client, shop, builder, qty=10, on=days_ago(40))  # 3950
    b = credit_bill(client, shop, builder, qty=5)  # 1975

    preview = client.post(
        "/api/receipts/preview", json={"party_id": builder, "amount": "5000"}
    ).json()
    assert [(p["ref_no"], p["amount"]) for p in preview["plan"]] == [
        (a["invoice_no"], "3950.00"),
        (b["invoice_no"], "1050.00"),
    ]

    r = pay(client, builder, "5000")
    assert r["receipt_no"] == f"RCPT/{FY}/0001"
    assert r["allocated"] == "5000.00" and r["unallocated"] == "0.00"
    assert r["balance_after"] == "925.00"
    assert open_bills(client, builder) == {b["invoice_no"]: "925.00"}
    detail = client.get(f"/api/sales/{b['id']}").json()
    assert (detail["paid"], detail["balance_due"]) == ("1050.00", "925.00")
    ledger_ok(client)


def test_overpayment_is_an_advance_that_pays_the_next_bill(client, shop, builder):
    r = pay(client, builder, "5000")
    assert r["unallocated"] == "5000.00"
    assert outstanding(client, builder) == "-5000.00"

    credit_bill(client, shop, builder)  # 3950, settled from the advance at once
    assert open_bills(client, builder) == {}
    assert outstanding(client, builder) == "-1050.00"
    ledger_ok(client)


def test_manual_allocation(client, shop, builder):
    a = credit_bill(client, shop, builder, on=days_ago(10))
    b = credit_bill(client, shop, builder)
    r = pay(
        client, builder, "1000", allocations=[{"kind": "invoice", "id": b["id"], "amount": "1000"}]
    )
    assert [x["ref_no"] for x in r["allocations"]] == [b["invoice_no"]]
    assert open_bills(client, builder) == {a["invoice_no"]: "3950.00", b["invoice_no"]: "2950.00"}

    too_much = {
        "client_ref": ref(),
        "party_id": builder,
        "amount": "500",
        "mode": "cash",
        "allocations": [{"kind": "invoice", "id": a["id"], "amount": "600"}],
    }
    assert client.post("/api/receipts", json=too_much).status_code == 400


def test_same_receipt_submitted_twice_is_saved_once(client, shop, builder):
    credit_bill(client, shop, builder)
    body = {
        "client_ref": ref(),
        "party_id": builder,
        "amount": "1000",
        "mode": "upi",
        "reference": "UTR1",
    }
    assert (
        client.post("/api/receipts", json=body).json()["id"]
        == client.post("/api/receipts", json=body).json()["id"]
    )
    assert outstanding(client, builder) == "2950.00"


# ---- Cheques --------------------------------------------------------------------------
def test_cheque_bounce_reopens_bills_and_adds_charge(client, shop, builder):
    bill = credit_bill(client, shop, builder)
    chq = pay(
        client,
        builder,
        "3950",
        mode="cheque",
        cheque_no="000123",
        bank_name="SBI",
        cheque_date=TODAY.isoformat(),
    )
    assert chq["cheque_status"] == "received"
    assert open_bills(client, builder) == {}

    pending = client.get("/api/cheques", params={"status": "pending"}).json()
    assert [c["cheque_no"] for c in pending] == ["000123"]

    client.post(f"/api/receipts/{chq['id']}/cheque", json={"action": "deposit"})
    r = client.post(f"/api/receipts/{chq['id']}/cheque", json={"action": "bounce", "charge": "500"})
    assert r.status_code == 200 and r.json()["cheque_status"] == "bounced"
    assert open_bills(client, builder) == {
        bill["invoice_no"]: "3950.00",
        f"BOUNCE-{chq['receipt_no']}": "500.00",
    }
    assert outstanding(client, builder) == "4450.00"

    # The billing screen now warns about this customer
    draft = {
        "party_id": builder,
        "payment_mode": "credit",
        "lines": [{"product_id": shop["opc"], "qty": 1, "rate": "395"}],
    }
    assert any(
        "bounced" in w for w in client.post("/api/sales/preview", json=draft).json()["warnings"]
    )
    ledger_ok(client)


def test_cheque_status_rules(client, shop, builder):
    chq = pay(client, builder, "100", mode="cheque", cheque_no="9")
    assert (
        client.post(f"/api/receipts/{chq['id']}/cheque", json={"action": "clear"}).status_code
        == 200
    )
    assert (
        client.post(f"/api/receipts/{chq['id']}/cheque", json={"action": "bounce"}).status_code
        == 400
    )
    assert (
        client.post(f"/api/receipts/{chq['id']}/cheque", json={"action": "deposit"}).status_code
        == 400
    )
    cash = pay(client, builder, "100")
    assert (
        client.post(f"/api/receipts/{cash['id']}/cheque", json={"action": "deposit"}).status_code
        == 400
    )


# ---- Cancels, returns, roles -------------------------------------------------------------
def test_cancelling_a_receipt_reopens_the_bill(client, shop, builder):
    bill = credit_bill(client, shop, builder)
    r = pay(client, builder, "3950")
    c = client.post(f"/api/receipts/{r['id']}/cancel", json={"reason": "Wrong customer"})
    assert c.status_code == 200 and c.json()["status"] == "cancelled"
    assert open_bills(client, builder) == {bill["invoice_no"]: "3950.00"}
    assert (
        client.post(f"/api/receipts/{r['id']}/cancel", json={"reason": "again"}).status_code == 400
    )
    ledger_ok(client)


def test_return_on_a_paid_bill_becomes_advance(client, shop, builder):
    bill = credit_bill(client, shop, builder)
    pay(client, builder, "3950")
    client.post(
        f"/api/sales/{bill['id']}/returns",
        json={"reason": "Excess", "items": [{"sales_line_id": bill["lines"][0]["id"], "qty": 2}]},
    )
    assert outstanding(client, builder) == "-790.00"  # 2 bags x 395 now held as advance
    ledger_ok(client)


def test_cancelling_a_paid_bill_moves_the_money_to_other_bills(client, shop, builder):
    a = credit_bill(client, shop, builder, on=days_ago(5))
    b = credit_bill(client, shop, builder)
    pay(client, builder, "3950")  # pays A
    client.post(f"/api/sales/{a['id']}/cancel", json={"reason": "Billed twice"})
    assert open_bills(client, builder) == {}  # B settled by the freed money
    assert outstanding(client, builder) == "0.00"
    assert b["grand_total"] == "3950.00"
    ledger_ok(client)


def test_roles(client, shop, builder, make_user):
    credit_bill(client, shop, builder)
    r = pay(client, builder, "100")
    client.post("/api/auth/logout")
    make_user("clerk", Role.BILLING)
    client.post("/api/auth/login", json={"username": "clerk", "password": PASSWORD})
    assert pay(client, builder, "100")["mode"] == "cash"  # counter cash is fine
    chq = {
        "client_ref": ref(),
        "party_id": builder,
        "amount": "10",
        "mode": "cheque",
        "cheque_no": "1",
    }
    assert client.post("/api/receipts", json=chq).status_code == 403
    assert (
        client.post(f"/api/receipts/{r['id']}/cancel", json={"reason": "nope"}).status_code == 403
    )
    assert client.get("/api/cheques").status_code == 403


# ---- Statement & ageing -------------------------------------------------------------------
def test_statement_running_balance(client, shop, builder):
    credit_bill(client, shop, builder, on=days_ago(20))  # 3950
    pay(client, builder, "1000")
    credit_bill(client, shop, builder, qty=5)  # 1975

    full = client.get(f"/api/parties/{builder}/ledger", params={"date_from": days_ago(30)}).json()
    assert full["opening"] == "0.00"
    assert [ln["balance"] for ln in full["lines"]] == ["3950.00", "2950.00", "4925.00"]
    assert full["closing"] == "4925.00"
    assert (full["total_debit"], full["total_credit"]) == ("5925.00", "1000.00")

    recent = client.get(f"/api/parties/{builder}/ledger", params={"date_from": days_ago(10)}).json()
    assert recent["opening"] == "3950.00"  # the older bill is brought forward
    assert recent["closing"] == "4925.00"


def test_ageing_buckets_and_overdue(client, shop):
    party = new_customer(client, days=30)
    for age in (10, 45, 75, 120):
        credit_bill(client, shop, party, qty=1, rate="1000", on=days_ago(age))
    rep = client.get("/api/reports/outstanding").json()
    row = next(r for r in rep["rows"] if r["party_id"] == party)
    assert (row["b0_30"], row["b31_60"], row["b61_90"], row["b90_plus"]) == (
        "1000.00",
        "1000.00",
        "1000.00",
        "1000.00",
    )
    assert row["due"] == "4000.00" and row["overdue"] == "3000.00"  # older than 30 days
    assert row["oldest_days"] == 120 and row["open_bills"] == 4


def test_opening_dues_are_paid_first(client, shop, builder):
    bill = credit_bill(client, shop, builder)
    r = client.post(
        f"/api/parties/{builder}/opening-dues",
        json={"ref_no": "OLD-17", "due_date": days_ago(200), "amount": "2500"},
    )
    assert r.status_code == 201
    pay(client, builder, "3000")
    assert open_bills(client, builder) == {bill["invoice_no"]: "3450.00"}
    rep = client.get("/api/reports/outstanding").json()
    assert next(x for x in rep["rows"] if x["party_id"] == builder)["b90_plus"] == "0.00"
    ledger_ok(client)


# ---- Property: the books always balance -----------------------------------------------------
actions = st.lists(
    st.one_of(
        st.tuples(st.just("bill"), st.integers(1, 40)),
        st.tuples(st.just("pay"), st.integers(1, 20000)),
        st.tuples(st.just("cheque"), st.integers(1, 20000)),
        st.tuples(st.just("bounce"), st.integers(0, 10)),
        st.tuples(st.just("return"), st.integers(0, 10)),
        st.tuples(st.just("cancel_bill"), st.integers(0, 10)),
        st.tuples(st.just("cancel_receipt"), st.integers(0, 10)),
    ),
    min_size=1,
    max_size=15,
)


@settings(
    max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(actions)
def test_ledger_always_matches_open_bills(client, shop, sequence):
    """Any mix of bills, payments, cheques, bounces, returns and cancels keeps:
    ledger balance == open bills - advance, and no bill is ever over- or under-paid."""
    party = new_customer(client)
    bills, receipts, cheques = [], [], []
    for action, n in sequence:
        if action == "bill":
            bills.append(credit_bill(client, shop, party, qty=n, rate="397.50"))
        elif action == "pay":
            receipts.append(pay(client, party, str(n)))
        elif action == "cheque":
            chq = pay(client, party, str(n), mode="cheque", cheque_no=str(n))
            receipts.append(chq)
            cheques.append(chq)
        elif action == "bounce" and cheques:
            c = cheques[n % len(cheques)]
            client.post(
                f"/api/receipts/{c['id']}/cheque", json={"action": "bounce", "charge": "250"}
            )
        elif action == "return" and bills:
            b = bills[n % len(bills)]
            client.post(
                f"/api/sales/{b['id']}/returns",
                json={
                    "reason": "test",
                    "items": [{"sales_line_id": b["lines"][0]["id"], "qty": 1}],
                },
            )
        elif action == "cancel_bill" and bills:
            client.post(f"/api/sales/{bills[n % len(bills)]['id']}/cancel", json={"reason": "test"})
        elif action == "cancel_receipt" and receipts:
            client.post(
                f"/api/receipts/{receipts[n % len(receipts)]['id']}/cancel", json={"reason": "test"}
            )

    ledger_ok(client)
    for b in client.get(f"/api/parties/{party}/open-bills").json():
        assert Decimal(b["balance"]) > 0 and Decimal(b["paid"]) >= 0
        assert Decimal(b["paid"]) < Decimal(b["amount"])
    for r in receipts:
        fresh = client.get(f"/api/receipts/{r['id']}").json()
        assert Decimal(fresh["allocated"]) <= Decimal(fresh["amount"])
        assert Decimal(fresh["unallocated"]) >= 0
