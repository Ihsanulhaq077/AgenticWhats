import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_business
from app.db.session import get_db
from app.models.entities import Business, Category, MenuItem
from app.schemas.api import MenuCategoryIn, MenuItemIn, MenuItemOut, MenuItemUpdateIn
from app.services.notification_service import write_audit

router = APIRouter(prefix="/menu", tags=["menu"])


@router.get("", response_model=list[MenuItemOut])
@router.get("/", response_model=list[MenuItemOut], include_in_schema=False)
def list_menu(business: Business = Depends(get_current_business), db: Session = Depends(get_db)):
    return (
        db.query(MenuItem).filter(MenuItem.business_id == business.id)
        .order_by(MenuItem.category_id, MenuItem.id).all()
    )


@router.get("/categories")
def list_categories(business: Business = Depends(get_current_business), db: Session = Depends(get_db)):
    return [{"id": c.id, "name": c.name}
            for c in db.query(Category).filter(Category.business_id == business.id).all()]


@router.post("/categories", status_code=201)
def create_category(
    payload: MenuCategoryIn,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    category = Category(business_id=business.id, name=payload.name)
    db.add(category)
    db.commit()
    return {"id": category.id, "name": category.name}


@router.post("", response_model=MenuItemOut, status_code=201)
def create_item(
    payload: MenuItemIn,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    if payload.category_id is not None:
        cat = db.query(Category).filter(
            Category.business_id == business.id, Category.id == payload.category_id).first()
        if cat is None:
            raise HTTPException(400, "category not found for this business")
    item = MenuItem(
        business_id=business.id,
        name=payload.name,
        description=payload.description,
        price=payload.price,
        category_id=payload.category_id,
        availability=1 if payload.availability else 0,
        currency=business.currency,
        metadata_json=json.dumps(payload.metadata),
    )
    db.add(item)
    db.commit()
    write_audit(db, business_id=business.id, actor_id=None, action="menu.create",
                entity_type="menu_item", entity_id=item.id)
    return item


@router.patch("/{item_id}", response_model=MenuItemOut)
def update_item(
    item_id: int,
    payload: MenuItemUpdateIn,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    item = db.query(MenuItem).filter(
        MenuItem.business_id == business.id, MenuItem.id == item_id).first()
    if item is None:
        raise HTTPException(404, "Menu item not found")
    data = payload.model_dump(exclude_unset=True)
    meta = data.pop("metadata", None)
    if "availability" in data:
        data["availability"] = 1 if data["availability"] else 0
    for field, value in data.items():
        setattr(item, field, value)
    if meta is not None:
        import json
        item.metadata_json = json.dumps(meta)
    db.commit()
    return item


@router.delete("/{item_id}", status_code=204)
def delete_item(
    item_id: int,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    item = db.query(MenuItem).filter(
        MenuItem.business_id == business.id, MenuItem.id == item_id).first()
    if item is None:
        raise HTTPException(404, "Menu item not found")
    db.delete(item)
    db.commit()
