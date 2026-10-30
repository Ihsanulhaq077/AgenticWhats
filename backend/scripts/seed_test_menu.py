"""Add a sample test menu to any business (by slug or id).

Usage:
  ./.venv/Scripts/python.exe backend/scripts/seed_test_menu.py ktr
  ./.venv/Scripts/python.exe backend/scripts/seed_test_menu.py 2
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal  # noqa: E402
from app.models.entities import Business, Category, MenuItem  # noqa: E402

TEST_MENU = [
    ("Pizza", [
        ("Chicken Tikka Pizza (Small)", "Chicken tikka chunks, onion, capsicum, mozzarella", 850),
        ("Chicken Fajita Pizza (Small)", "Fajita chicken, jalapenos, cheese blend", 900),
        ("Cheese Lover Pizza (Small)", "Triple cheese blend with tomato sauce", 800),
        ("BBQ Chicken Pizza (Large)", "BBQ chicken, onion, extra cheese", 1500),
    ]),
    ("Burgers", [
        ("Zinger Burger", "Crispy spicy chicken fillet, mayo, lettuce", 450),
        ("Beef Cheese Burger", "Grilled beef patty with cheddar", 550),
        ("Double Decker Burger", "Two chicken fillets, cheese, special sauce", 700),
    ]),
    ("Wraps & Rolls", [
        ("Chicken Shawarma", "Grilled chicken, garlic sauce, pickles", 250),
        ("Zinger Wrap", "Crispy chicken, cheesy sauce, lettuce", 320),
        ("Beef Roll Paratha", "Spicy beef in flaky paratha", 350),
    ]),
    ("Sides", [
        ("French Fries (Regular)", "Crispy golden fries with salt", 180),
        ("Loaded Fries", "Fries with chicken chunks, cheese sauce, jalapenos", 420),
        ("Chicken Nuggets (6 pcs)", "Crispy nuggets with dip", 300),
        ("Onion Rings", "Crunchy battered onion rings", 250),
    ]),
    ("Drinks", [
        ("Soft Drink (Regular)", "Chilled soft drink", 90),
        ("Mint Margarita", "Fresh mint, lemon, soda", 220),
        ("Mineral Water", "500ml bottled water", 60),
    ]),
    ("Deals", [
        ("Deal 1: Zinger + Fries + Drink", "Zinger burger, regular fries, soft drink", 650),
        ("Deal 2: 2 Pizzas + 1.5L Drink", "Two small pizzas with a large drink", 1800),
        ("Deal 3: Family Feast", "1 large pizza, 2 burgers, loaded fries, 1.5L drink", 2500),
    ]),
]


def main() -> None:
    key = sys.argv[1] if len(sys.argv) > 1 else "ktr"
    db = SessionLocal()
    try:
        business = None
        if key.isdigit():
            business = db.get(Business, int(key))
        if business is None:
            business = db.query(Business).filter(Business.slug == key).first()
        if business is None:
            print(f"Business not found: {key!r}")
            sys.exit(1)

        existing = db.query(MenuItem).filter(MenuItem.business_id == business.id).count()
        if existing:
            print(f"Business {business.name!r} already has {existing} menu items — nothing added.")
            return

        total = 0
        for cat_name, items in TEST_MENU:
            category = Category(business_id=business.id, name=cat_name)
            db.add(category)
            db.flush()
            for name, desc, price in items:
                db.add(MenuItem(
                    business_id=business.id, category_id=category.id,
                    name=name, description=desc, price=price,
                    currency=business.currency or "PKR", availability=1,
                ))
                total += 1
        db.commit()
        print(f"Added {total} test menu items to {business.name!r} (business id={business.id}).")
        print("Refresh the Menu page in the dashboard to see them.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
