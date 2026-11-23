from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from app.services.money import allocate, q2, round_off, split_gst

paise_amounts = st.integers(min_value=0, max_value=10**10).map(lambda p: Decimal(p) / 100)
weights = st.lists(st.integers(min_value=0, max_value=10**6).map(Decimal), min_size=1, max_size=20)


@given(paise_amounts, weights)
def test_allocation_never_loses_or_invents_a_paisa(total, ws):
    parts = allocate(total, ws)
    assert sum(parts, Decimal(0)) == total
    assert all(p >= 0 for p in parts)
    assert all(p == q2(p) for p in parts)


@given(paise_amounts, weights)
def test_allocation_is_proportional_within_a_paisa(total, ws):
    parts = allocate(total, ws)
    w_sum = sum(ws, Decimal(0))
    if w_sum == 0:
        return
    for part, w in zip(parts, ws, strict=True):
        assert abs(part - total * w / w_sum) < Decimal("0.01")


def test_allocation_example():
    # 3450 of freight over 5000 kg and 2500 kg
    assert allocate(Decimal("3450"), [Decimal(5000), Decimal(2500)]) == [
        Decimal("2300.00"),
        Decimal("1150.00"),
    ]
    assert allocate(Decimal("100"), [Decimal(1)] * 3) == [
        Decimal("33.34"),
        Decimal("33.33"),
        Decimal("33.33"),
    ]


@given(paise_amounts)
def test_cgst_sgst_always_add_back(gst):
    cgst, sgst = split_gst(gst)
    assert cgst + sgst == gst
    assert abs(cgst - sgst) <= Decimal("0.01")


@given(paise_amounts)
def test_round_off_makes_whole_rupees(total):
    ro = round_off(total)
    assert abs(ro) <= Decimal("0.50")
    assert (total + ro) % 1 == 0


def test_round_off_half_goes_up():
    assert round_off(Decimal("100.50")) == Decimal("0.50")
    assert round_off(Decimal("100.49")) == Decimal("-0.49")
