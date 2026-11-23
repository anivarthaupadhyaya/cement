import contextlib
import itertools
from datetime import date
from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models import Brand, Product, StockBalance, StockMovement
from app.services import stock

TODAY = date(2026, 11, 20)
GODOWN = 1  # "Main Godown" from the seed migration
_counter = itertools.count()


def new_product(db: Session) -> Product:
    brand = Brand(name=f"Test brand {next(_counter)}")
    db.add(brand)
    db.flush()
    product = Product(brand_id=brand.id, grade="PPC")
    db.add(product)
    db.flush()
    return product


def balance(db: Session, product_id: int) -> StockBalance:
    db.flush()
    bal = db.get(StockBalance, (product_id, GODOWN), populate_existing=True)
    assert bal is not None
    return bal


def test_weighted_average_cost(db):
    p = new_product(db)
    stock.stock_in(db, p.id, GODOWN, 100, Decimal("300"), stock.Ref("purchase"), TODAY)
    stock.stock_in(db, p.id, GODOWN, 50, Decimal("330"), stock.Ref("purchase"), TODAY)
    assert balance(db, p.id).avg_cost == Decimal("310.0000")

    out = stock.stock_out(db, p.id, GODOWN, 30, stock.Ref("sale"), TODAY)
    assert out.unit_cost == Decimal("310.0000")  # goes out at average
    assert balance(db, p.id).qty == 120
    assert balance(db, p.id).avg_cost == Decimal("310.0000")  # unchanged by sales


def test_reversing_a_purchase_restores_the_previous_average(db):
    p = new_product(db)
    stock.stock_in(db, p.id, GODOWN, 100, Decimal("300"), stock.Ref("purchase"), TODAY)
    stock.stock_in(db, p.id, GODOWN, 50, Decimal("330"), stock.Ref("purchase"), TODAY)
    stock.reverse_in(db, p.id, GODOWN, 50, Decimal("330"), stock.Ref("purchase_cancel"), TODAY)
    bal = balance(db, p.id)
    assert (bal.qty, bal.avg_cost) == (100, Decimal("300.0000"))


def test_cannot_sell_more_than_in_stock(db):
    p = new_product(db)
    stock.stock_in(db, p.id, GODOWN, 10, Decimal("300"), stock.Ref("purchase"), TODAY)
    with pytest.raises(stock.InsufficientStock) as err:
        stock.stock_out(db, p.id, GODOWN, 11, stock.Ref("sale"), TODAY)
    assert err.value.available == 10
    assert balance(db, p.id).qty == 10


def test_database_refuses_negative_balance_even_if_code_is_bypassed(db):
    p = new_product(db)
    stock.stock_in(db, p.id, GODOWN, 5, Decimal("300"), stock.Ref("purchase"), TODAY)
    db.flush()
    with pytest.raises(DBAPIError, match="ck_stock_balances_non_negative"):
        db.execute(text("UPDATE stock_balances SET qty = -1 WHERE product_id = :p"), {"p": p.id})


def test_movements_are_append_only(db):
    p = new_product(db)
    stock.stock_in(db, p.id, GODOWN, 5, Decimal("300"), stock.Ref("purchase"), TODAY)
    db.flush()
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("UPDATE stock_movements SET qty = 500 WHERE product_id = :p"), {"p": p.id})


ops = st.lists(
    st.tuples(
        st.sampled_from(["in", "out"]),
        st.integers(min_value=1, max_value=500),
        st.integers(min_value=25000, max_value=45000).map(lambda paise: Decimal(paise) / 100),
    ),
    min_size=1,
    max_size=30,
)


@settings(
    max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(ops)
def test_stock_invariants_hold_for_any_sequence(db, sequence):
    """Whatever happens: no negative stock, balance == SUM(movements), avg within cost range."""
    p = new_product(db)
    costs_in: list[Decimal] = []
    for op, qty, cost in sequence:
        if op == "in":
            stock.stock_in(db, p.id, GODOWN, qty, cost, stock.Ref("purchase"), TODAY)
            costs_in.append(cost)
        else:
            with contextlib.suppress(stock.InsufficientStock):
                stock.stock_out(db, p.id, GODOWN, qty, stock.Ref("sale"), TODAY)
    db.flush()

    bal = db.get(StockBalance, (p.id, GODOWN), populate_existing=True)
    total = db.scalar(
        select(func.coalesce(func.sum(StockMovement.qty), 0)).where(
            StockMovement.product_id == p.id
        )
    )
    qty = bal.qty if bal else 0
    assert qty >= 0
    assert qty == total
    if bal and bal.qty > 0:
        assert (
            min(costs_in) - Decimal("0.0001") <= bal.avg_cost <= max(costs_in) + Decimal("0.0001")
        )
    assert stock.verify_balances(db) == []
