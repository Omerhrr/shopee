"""Database models - Shopee dropshipping platform."""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20), default="admin")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[object] = mapped_column(JSON)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name_en: Mapped[str] = mapped_column(String(120))
    name_ko: Mapped[str] = mapped_column(String(120))
    markup_percent: Mapped[float | None] = mapped_column(Float, nullable=True)  # overrides global
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Source(Base):
    """A wholesale supplier site that listings are scraped from (from the uploaded Excel list)."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), index=True)
    url: Mapped[str] = mapped_column(String(500), default="")
    category_hint: Mapped[str] = mapped_column(String(120), default="")   # Korean category from the sheet
    products_hint: Mapped[str] = mapped_column(String(200), default="")
    contact: Mapped[str] = mapped_column(String(120), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    image_provided: Mapped[bool] = mapped_column(Boolean, default=True)
    dropship_possible: Mapped[bool] = mapped_column(Boolean, default=True)
    paid_membership: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_cafe: Mapped[bool] = mapped_column(Boolean, default=False)

    adapter: Mapped[str] = mapped_column(String(40), default="generic")  # generic | manual
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # {"listing_url":..., "max_products":..., "category_id":...}
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="new")  # new | ok | error
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")

    products: Mapped[list["Product"]] = relationship(back_populates="source")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(220), unique=True, index=True)
    title_ko: Mapped[str] = mapped_column(String(300), default="")
    title_en: Mapped[str | None] = mapped_column(String(300), nullable=True)
    desc_ko: Mapped[str] = mapped_column(Text, default="")
    desc_en: Mapped[str | None] = mapped_column(Text, nullable=True)

    price_cost: Mapped[int] = mapped_column(Integer, default=0)     # wholesale price in KRW
    price_sell: Mapped[int] = mapped_column(Integer, default=0)     # retail = cost + markup
    markup_override: Mapped[float | None] = mapped_column(Float, nullable=True)

    images: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="published")  # published | draft
    original_lang: Mapped[str] = mapped_column(String(10), default="ko")
    translation_status: Mapped[str] = mapped_column(String(20), default="pending")  # done | pending | failed | none
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    rating: Mapped[float] = mapped_column(Float, default=4.7)
    reviews: Mapped[int] = mapped_column(Integer, default=0)
    stock_status: Mapped[str] = mapped_column(String(20), default="in_stock")

    source_url: Mapped[str | None] = mapped_column(String(600), nullable=True, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    category: Mapped["Category | None"] = relationship(back_populates="products")
    source: Mapped["Source | None"] = relationship(back_populates="products")


class ScrapeLog(Base):
    __tablename__ = "scrape_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_name: Mapped[str] = mapped_column(String(150), default="")
    trigger: Mapped[str] = mapped_column(String(20), default="manual")  # manual | schedule
    status: Mapped[str] = mapped_column(String(20), default="ok")       # ok | error
    new_products: Mapped[int] = mapped_column(Integer, default=0)
    updated_products: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_number: Mapped[str] = mapped_column(String(30), unique=True, index=True)

    customer_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(60), default="")
    address1: Mapped[str] = mapped_column(String(300), default="")
    address2: Mapped[str] = mapped_column(String(300), default="")
    city: Mapped[str] = mapped_column(String(120), default="")
    postal_code: Mapped[str] = mapped_column(String(30), default="")
    memo: Mapped[str] = mapped_column(Text, default="")

    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending | paid | packed | shipped | delivered | cancelled
    payment_method: Mapped[str] = mapped_column(String(30), default="card")  # card | bank
    locale: Mapped[str] = mapped_column(String(10), default="en")

    subtotal: Mapped[int] = mapped_column(Integer, default=0)
    shipping: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    cost_total: Mapped[int] = mapped_column(Integer, default=0)
    profit: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    title_ko: Mapped[str] = mapped_column(String(300), default="")
    title_en: Mapped[str] = mapped_column(String(300), default="")
    image: Mapped[str] = mapped_column(String(600), default="")
    unit_sell: Mapped[int] = mapped_column(Integer, default=0)
    unit_cost: Mapped[int] = mapped_column(Integer, default=0)
    quantity: Mapped[int] = mapped_column(Integer, default=1)

    order: Mapped["Order"] = relationship(back_populates="items")


class MediaFile(Base):
    """Image bytes kept in the database when the host has no persistent disk (Vercel)."""

    __tablename__ = "media_files"

    path: Mapped[str] = mapped_column(String(400), primary_key=True)  # e.g. scraped/12/abc.jpg
    content_type: Mapped[str] = mapped_column(String(80), default="application/octet-stream")
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
