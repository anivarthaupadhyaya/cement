"""Load demo data into a DEVELOPMENT database (safe to run repeatedly).

python -m app.dev_seed
"""

import sys
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import Brand, Party, Product, Purchase
from app.services.gst import gstin_checksum
from app.services.pricing import set_prices
from app.services.purchases import LineInput, create_purchase

BRANDS = {
    "UltraTech": [("OPC 53", "420"), ("PPC", "395")],
    "ACC": [("OPC 53", "415"), ("PPC", "385")],
    "Ambuja": [("PPC", "390")],
    "Dalmia": [("PSC", "370")],
}

PARTIES = [
    ("customer", "Sri Lakshmi Traders", "9845012345", "29AAPFL4321K1Z", "Udupi", "200000", 30),
    ("customer", "Coastal Builders", "9008123456", "29AAGCC7788M1Z", "Manipal", "500000", 45),
    ("customer", "Ramesh (walk-in)", "9741000111", None, "Kundapura", "0", 0),
    ("supplier", "UltraTech CFA Mangaluru", "8242456789", "29AAACU1234F1Z", "Mangaluru", "0", 0),
]


def main() -> None:
    if "localhost" not in get_settings().database_url and "--force" not in sys.argv:
        sys.exit("Refusing to seed a non-local database (pass --force if you really mean it)")

    with SessionLocal() as db:
        today = date.today()
        for brand_name, grades in BRANDS.items():
            brand = db.scalar(select(Brand).where(Brand.name == brand_name))
            if brand is None:
                brand = Brand(name=brand_name)
                db.add(brand)
                db.flush()
            for grade, rate in grades:
                product = db.scalar(
                    select(Product).where(Product.brand_id == brand.id, Product.grade == grade)
                )
                if product is None:
                    product = Product(brand_id=brand.id, grade=grade, reorder_level=100)
                    db.add(product)
                    db.flush()
                # A rate from last week and today's (slightly higher) rate.
                old = Decimal(rate) - 10
                set_prices(db, [(product.id, old)], today - timedelta(days=7))
                set_prices(db, [(product.id, Decimal(rate))], today)

        for kind, name, phone, gstin14, area, limit, days in PARTIES:
            if db.scalar(select(Party.id).where(Party.name == name)):
                continue
            gstin = gstin14 + gstin_checksum(gstin14) if gstin14 else None
            db.add(
                Party(
                    kind=kind,
                    name=name,
                    phone=phone,
                    gstin=gstin,
                    state_code=gstin[:2] if gstin else "29",
                    area=area,
                    credit_limit=Decimal(limit),
                    credit_days=days,
                )
            )
        db.flush()

        # One truckload from the CFA so the stock page has something in it.
        if db.scalar(select(Purchase.id).limit(1)) is None:
            supplier = db.scalar(select(Party).where(Party.kind == "supplier"))
            products = db.scalars(select(Product).order_by(Product.id)).all()
            assert supplier is not None
            create_purchase(
                db,
                supplier=supplier,
                supplier_invoice_no="UT/DEMO/0001",
                invoice_date=today - timedelta(days=2),
                received_date=today - timedelta(days=1),
                godown_id=1,
                vehicle_no="KA20AB1234",
                freight=Decimal("4500"),
                unloading=Decimal("600"),
                lines=[
                    LineInput(products[0].id, 200, 197, 3, Decimal("335")),
                    LineInput(products[1].id, 150, 150, 0, Decimal("310")),
                    LineInput(products[2].id, 50, 48, 0, Decimal("330")),
                ],
            )
        db.commit()
    print("Demo data loaded.")


if __name__ == "__main__":
    main()
