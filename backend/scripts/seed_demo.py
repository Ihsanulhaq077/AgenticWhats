"""Seed the demo tenant: Khyber Taste Restaurant (synthetic demo data — spec §27).

Creates a platform admin, the demo restaurant with menu, knowledge base,
demo customers and WhatsApp account. Idempotent: safe to run repeatedly.

Usage: ./.venv/Scripts/python.exe backend/scripts/seed_demo.py
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.entities import (  # noqa: E402
    AISetting, Base, Business, BusinessUser, Category, Customer, MenuItem, Subscription, User,
    WhatsAppAccount,
)
from app.rag.ingestion import ingest_document  # noqa: E402

settings = get_settings()

MENU = [
    ("Rice & Biryani", [
        ("Chicken Biryani", "Fragrant basmati rice with tender chicken and Peshawari spices.", 450, True),
        ("Beef Biryani", "Slow-cooked beef layered with spiced basmati rice.", 550, True),
        ("Plain Pulao", "Aromatic rice pulao with mild spices.", 350, True),
    ]),
    ("Curries & Karahi", [
        ("Chicken Karahi", "Half-kg chicken karahi cooked in tomatoes, ginger and green chilli.", 1400, True),
        ("Beef Karahi", "Half-kg beef karahi, Peshawari style.", 1800, True),
        ("Chicken Tikka Masala", "Grilled chicken tikka in a creamy tomato gravy.", 950, False),
    ]),
    ("Burgers", [
        ("Beef Burger", "Char-grilled beef patty, cheddar, lettuce and house sauce.", 550, True),
        ("Chicken Burger", "Crispy chicken fillet with mayo and fresh salad.", 480, True),
        ("Zinger Burger", "Extra crispy spicy chicken fillet.", 560, True),
    ]),
    ("Fast Food", [
        ("Chicken Fries", "Crispy golden fries.", 180, True),
        ("Loaded Fries", "Fries topped with chicken, cheese and jalapeños.", 380, True),
    ]),
    ("Drinks", [
        ("Soft Drink", "Chilled soft drink can.", 90, True),
        ("Fresh Lime Soda", "Lime, soda, mint and black salt.", 150, True),
    ]),
]

KNOWLEDGE_DOCS = [
    ("Business Hours & Holidays", """Q: What are your opening hours?
A: We are open every day from 11:00 AM to 11:00 PM (PKT). The kitchen takes last orders at 10:30 PM.

Q: Are you open on Eid and public holidays?
A: We are closed on the first day of Eid-ul-Fitr and Eid-ul-Adha. On other public holidays we follow normal hours.

Q: When is your Friday break?
A: On Friday we pause dine-in from 1:00 PM to 2:30 PM for Jummah prayer. Delivery continues."""),
    ("Delivery Policy", """Q: Which areas do you deliver to?
A: We deliver across University Road, Board Bazaar, Tehkal, Palosi, Phase 3-5 Hayatabad, and Saddar Bazaar in Peshawar.

Q: What are the delivery charges?
A: Delivery is PKR 100 flat within 5 km. Orders above PKR 2,000 get free delivery inside our standard areas.

Q: How long does delivery take?
A: Normally 35-50 minutes depending on distance and kitchen load.

Q: What is the minimum order for delivery?
A: Minimum delivery order is PKR 500."""),
    ("Payment & Refund Policy", """Q: What payment methods do you accept?
A: Cash on delivery, JazzCash, Easypaisa, and bank transfer. Card machines are available at the restaurant counter only.

Q: What is your refund policy?
A: If an item is wrong or spilled, report within 30 minutes of delivery with a photo; we replace the item or refund that item's amount within 3 working days.

Q: Can I pay online?
A: Yes, we send a secure payment link for JazzCash or Easypaisa on request."""),
    ("Booking Policy", """Q: Do you take table reservations?
A: Yes. Tables can be booked from 11:00 AM to 10:30 PM for up to 20 guests per slot. Family hall is separate.

Q: How far in advance can I book?
A: Up to 14 days in advance. For groups above 12, please book at least one day ahead.

Q: How long is my table held?
A: We hold reserved tables for 20 minutes past the booking time."""),
]

DEMO_CUSTOMERS = [
    ("+923001112233", "Ahmed Khan", "roman_urdu"),
    ("+923004445566", "Fatima Bibi", "en"),
]


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Platform admin
        if not db.query(User).filter(User.email == "admin@agenticwhats.com").first():
            db.add(User(name="Platform Admin", email="admin@agenticwhats.com",
                        password_hash=hash_password("admin1234"), role="platform_admin"))
            db.commit()
            print("Created platform admin: admin@agenticwhats.com / admin1234")

        # Demo business
        business = db.query(Business).filter(Business.slug == "khyber-taste").first()
        if business is None:
            business = Business(
                name="Khyber Taste Restaurant",
                slug="khyber-taste",
                business_type="restaurant",
                description="Authentic Peshawari cuisine, biryani, karahi and fast food. "
                            "(Demo business with synthetic seed data)",
                address="Shop 12, University Road, Peshawar",
                phone="+92 91 555 0000",
                currency="PKR",
                settings=json.dumps({
                    "business_hours": {
                        "monday": "11:00-23:00", "tuesday": "11:00-23:00", "wednesday": "11:00-23:00",
                        "thursday": "11:00-23:00", "friday": "11:00-13:00, 14:30-23:00",
                        "saturday": "11:00-23:00", "sunday": "11:00-23:00",
                    },
                    "delivery_available": True,
                    "delivery_fee": 100,
                    "delivery_areas": ["University Road", "Board Bazaar", "Tehkal", "Palosi",
                                       "Hayatabad Phase 3-5", "Saddar Bazaar"],
                    "min_order": 500,
                    "booking_capacity_per_slot": 40,
                    "booking_slot_minutes": 60,
                    "cancellable_statuses": ["pending", "confirmed", "preparing"],
                }),
            )
            db.add(business)
            db.flush()
            print(f"Created demo business: {business.name} (id={business.id})")
        else:
            print(f"Demo business already exists (id={business.id})")

        # Owner user
        owner_email = settings.demo_owner_email
        owner = db.query(User).filter(User.email == owner_email).first()
        if owner is None:
            owner = User(name="Demo Owner", email=owner_email,
                         password_hash=hash_password(settings.demo_owner_password), role="owner")
            db.add(owner)
            db.flush()
            db.add(BusinessUser(business_id=business.id, user_id=owner.id, role="owner"))
            print(f"Created demo owner: {owner_email} / {settings.demo_owner_password}")
        elif not db.query(BusinessUser).filter(
                BusinessUser.business_id == business.id, BusinessUser.user_id == owner.id).first():
            db.add(BusinessUser(business_id=business.id, user_id=owner.id, role="owner"))

        if db.query(AISetting).filter(AISetting.business_id == business.id).first() is None:
            db.add(AISetting(business_id=business.id, agent_name="Sara",
                             instructions="Always greet politely. Special offer: free Fresh Lime Soda "
                                          "on orders above PKR 2,000. Escalate all refund requests to staff."))

        if db.query(Subscription).filter(Subscription.business_id == business.id).first() is None:
            db.add(Subscription(business_id=business.id, plan="business", status="active",
                                renewal_date=datetime.utcnow() + timedelta(days=30)))

        if db.query(WhatsAppAccount).filter(WhatsAppAccount.business_id == business.id).first() is None:
            db.add(WhatsAppAccount(business_id=business.id, phone_number_id="DEMO-PHONE-ID",
                                   display_phone="+92 91 555 0000", status="connected",
                                   access_token_reference="env:WHATSAPP_ACCESS_TOKEN"))

        # Menu
        if db.query(MenuItem).filter(MenuItem.business_id == business.id).count() == 0:
            for cat_name, items in MENU:
                category = Category(business_id=business.id, name=cat_name)
                db.add(category)
                db.flush()
                for name, desc, price, available in items:
                    db.add(MenuItem(business_id=business.id, category_id=category.id, name=name,
                                    description=desc, price=price, currency="PKR",
                                    availability=1 if available else 0))
            print(f"Seeded menu: {sum(len(i) for _, i in MENU)} items")
        else:
            print("Menu already seeded")

        # Demo customers
        for number, name, lang in DEMO_CUSTOMERS:
            if db.query(Customer).filter(
                    Customer.business_id == business.id, Customer.whatsapp_number == number).first() is None:
                db.add(Customer(business_id=business.id, whatsapp_number=number, name=name, language=lang))

        db.commit()

        # Knowledge base (RAG)
        for title, content in KNOWLEDGE_DOCS:
            ingest_document(db, business.id, title, content, source_type="faq")
        print(f"Seeded knowledge base: {len(KNOWLEDGE_DOCS)} documents")

        print("\nDEMO TENANT READY (all data is synthetic demo data)")
        print(f"  Business id : {business.id}")
        print(f"  WhatsApp pnid: DEMO-PHONE-ID (webhook simulator targets this)")
        print(f"  Owner login : {settings.demo_owner_email} / {settings.demo_owner_password}")
        print(f"  Admin login : admin@agenticwhats.com / admin1234")
    finally:
        db.close()


if __name__ == "__main__":
    main()
