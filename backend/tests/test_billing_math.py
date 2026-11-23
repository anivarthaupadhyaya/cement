from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.services.billing import calc_bill, split_inclusive
from app.services.numbering import financial_year
from app.services.words import number_in_words, rupees_in_words

D = Decimal


def test_inclusive_rate_example():
    # 10 bags at Rs 395 incl. 18% GST
    taxable, gst = split_inclusive(D("3950.00"), D("18"))
    assert (taxable, gst) == (D("3347.46"), D("602.54"))


def test_bill_example_with_delivery():
    bill = calc_bill([(10, D("395"), D("18")), (5, D("420"), D("18"))], D("300"))
    assert bill.taxable_total + bill.gst_total == D("3950") + D("2100") + D("300")
    assert bill.grand_total == D("6350.00")
    assert bill.round_off == D("0.00")


lines = st.lists(
    st.tuples(
        st.integers(min_value=1, max_value=2000),
        st.integers(min_value=100, max_value=100_000).map(lambda p: D(p) / 100),
        st.sampled_from([D("0"), D("5"), D("12"), D("18"), D("28")]),
    ),
    min_size=1,
    max_size=10,
)
delivery = st.integers(min_value=0, max_value=500_000).map(lambda p: D(p) / 100)


@given(lines, delivery)
def test_customer_pays_exactly_what_was_agreed(ls, d):
    """taxable + GST equals bags x agreed rate (+ delivery) to the paisa; total is whole rupees."""
    bill = calc_bill(ls, d)
    agreed = sum((D(q) * r for q, r, _ in ls), D(0)) + d
    for (q, r, _), amt in zip(ls, bill.lines, strict=True):
        assert amt.taxable + amt.gst == D(q) * r
    assert bill.taxable_total + bill.gst_total == agreed
    assert bill.grand_total == bill.taxable_total + bill.gst_total + bill.round_off
    assert bill.grand_total % 1 == 0
    assert abs(bill.grand_total - agreed) <= D("0.50")


@given(lines)
def test_gst_is_never_negative_or_more_than_rate_allows(ls):
    bill = calc_bill(ls)
    for (_, _, rate), amt in zip(ls, bill.lines, strict=True):
        assert amt.gst >= 0
        assert abs(amt.gst - amt.taxable * rate / 100) <= D("0.01")


@pytest.mark.parametrize(
    ("n", "words"),
    [
        (0, "Zero"),
        (15, "Fifteen"),
        (100, "One Hundred"),
        (1005, "One Thousand Five"),
        (100000, "One Lakh"),
        (12345678, "One Crore Twenty Three Lakh Forty Five Thousand Six Hundred Seventy Eight"),
    ],
)
def test_number_in_words_indian_system(n, words):
    assert number_in_words(n) == words


def test_rupees_in_words():
    assert rupees_in_words(D("125430.50")) == (
        "Rupees One Lakh Twenty Five Thousand Four Hundred Thirty and Fifty Paise Only"
    )
    assert rupees_in_words(D("6350")) == "Rupees Six Thousand Three Hundred Fifty Only"


@pytest.mark.parametrize(
    ("d", "fy"),
    [
        (date(2026, 3, 31), "2025-26"),
        (date(2026, 4, 1), "2026-27"),
        (date(2026, 11, 23), "2026-27"),
        (date(2099, 12, 1), "2099-00"),
    ],
)
def test_financial_year(d, fy):
    assert financial_year(d) == fy
