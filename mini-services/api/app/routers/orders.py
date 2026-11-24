"""Public orders API - guest checkout (demo payment) + order tracking."""
import random
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import get_setting
from ..serializers import order_admin

router = APIRouter(prefix="/api/orders", tags=["orders"])


class CheckoutItem(BaseModel):
    slug: str
    quantity: int = 1


class Customer(BaseModel):
    name: str
    email: str = ""
    phone: str
    address1: str
    address2: str = ""
    city: str = ""
    postal_code: str = ""
    memo: str = ""


class CheckoutIn(BaseModel):
    items: list[CheckoutItem]
    customer: Customer
    payment_method: str = "card"  # card (demo instant) | bank (pending)
    locale: str = "en"


@router.post("")
def create_order(body: CheckoutIn, db: Session = Depends(get_db)):
    if not body.items:
        raise HTTPException(400, "Cart is empty")
    if not body.customer.name or not body.customer.address1:
        raise HTTPException(400, "Name and address are required")

    subtotal = cost_total = 0
    order = models.Order(
        order_number="SP" + datetime.now().strftime("%y%m%d") + f"{random.randint(1000, 9999)}",
        customer_name=body.customer.name,
        email=body.customer.email,
        phone=body.customer.phone,
        address1=body.customer.address1,
        address2=body.customer.address2,
        city=body.customer.city,
        postal_code=body.customer.postal_code,
        memo=body.customer.memo,
        payment_method=body.payment_method,
        locale=body.locale,
        status="paid" if body.payment_method == "card" else "pending",
    )

    for it in body.items:
        p = (
            db.query(models.Product)
            .filter(models.Product.slug == it.slug, models.Product.status == "published")
            .first()
        )
        if not p:
            raise HTTPException(400, f"Product unavailable: {it.slug}")
        qty = max(1, min(it.quantity, 99))
        subtotal += p.price_sell * qty
        cost_total += p.price_cost * qty
        order.items.append(
            models.OrderItem(
                product_id=p.id,
                title_ko=p.title_ko,
                title_en=p.title_en or p.title_ko,
                image=(p.images or [""])[0],
                unit_sell=p.price_sell,
                unit_cost=p.price_cost,
                quantity=qty,
            )
        )

    threshold = int(get_setting(db, "free_shipping_threshold", 50000))
    flat = int(get_setting(db, "shipping_flat", 2500))
    order.subtotal = subtotal
    order.shipping = 0 if subtotal >= threshold else flat
    order.total = subtotal + order.shipping
    order.cost_total = cost_total
    order.profit = subtotal - cost_total
    db.add(order)
    db.commit()
    return {"order_number": order.order_number, "total": order.total, "status": order.status}


@router.get("/{order_number}")
def get_order(order_number: str, db: Session = Depends(get_db)):
    o = db.query(models.Order).filter(models.Order.order_number == order_number).first()
    if not o:
        raise HTTPException(404, "Order not found")
    return order_admin(o)
