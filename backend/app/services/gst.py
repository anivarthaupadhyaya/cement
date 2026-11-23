"""GSTIN validation and GST state codes.

A GSTIN is 15 characters: 2-digit state code, 10-char PAN, entity number, 'Z', checksum.
The checksum is a weighted base-36 sum over the first 14 characters.
"""

import re

GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

STATE_CODES: dict[str, str] = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
    "97": "Other Territory",
}


def gstin_checksum(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        product = _CHARS.index(ch) * (1 if i % 2 == 0 else 2)
        total += product // 36 + product % 36
    return _CHARS[(36 - total % 36) % 36]


def normalize_gstin(value: str) -> str:
    return value.strip().upper()


def validate_gstin(value: str) -> str:
    """Return the normalized GSTIN or raise ValueError with a human-readable reason."""
    gstin = normalize_gstin(value)
    if not GSTIN_RE.match(gstin):
        raise ValueError("GSTIN must be 15 characters like 29ABCDE1234F1Z5")
    if gstin[:2] not in STATE_CODES:
        raise ValueError(f"Unknown state code {gstin[:2]} in GSTIN")
    if gstin_checksum(gstin[:14]) != gstin[14]:
        raise ValueError("GSTIN check digit doesn't match; please re-check the number")
    return gstin


def is_interstate(seller_state: str, buyer_state: str) -> bool:
    """Inter-state supply → IGST; same state → CGST + SGST."""
    return seller_state != buyer_state
