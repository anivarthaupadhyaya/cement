import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.services.gst import (
    _CHARS,
    STATE_CODES,
    gstin_checksum,
    is_interstate,
    validate_gstin,
)

UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGITS = "0123456789"


def make_gstin(state: str, pan_letters: str, pan_digits: str, pan_last: str, entity: str) -> str:
    body = f"{state}{pan_letters}{pan_digits}{pan_last}{entity}Z"
    return body + gstin_checksum(body)


gstins = st.builds(
    make_gstin,
    st.sampled_from(sorted(STATE_CODES)),
    st.text(UPPER, min_size=5, max_size=5),
    st.text(DIGITS, min_size=4, max_size=4),
    st.sampled_from(UPPER),
    st.sampled_from("123456789" + UPPER),
)


def test_known_valid_gstin():
    gstin = make_gstin("29", "AAACU", "1234", "F", "1")
    assert validate_gstin(gstin.lower()) == gstin  # normalised to upper case


@pytest.mark.parametrize(
    "bad",
    ["", "29AAACU1234F1Z", "29AAACU1234F1X5", "99AAACU1234F1Z5", "2AAAACU1234F1Z5"],
)
def test_rejects_malformed(bad):
    with pytest.raises(ValueError):
        validate_gstin(bad)


@given(gstins)
def test_generated_gstins_validate(gstin):
    assert validate_gstin(gstin) == gstin


@given(gstins, st.integers(min_value=0, max_value=14), st.sampled_from(_CHARS))
def test_any_single_character_typo_is_caught(gstin, pos, ch):
    """The mod-36 check digit catches every single-character substitution."""
    if gstin[pos] == ch:
        return
    typo = gstin[:pos] + ch + gstin[pos + 1 :]
    with pytest.raises(ValueError):
        validate_gstin(typo)


def test_interstate():
    assert is_interstate("29", "33")
    assert not is_interstate("29", "29")
