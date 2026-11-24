"""Pricing rules: cost (wholesale KRW) + markup% => retail price."""


def resolve_markup(product, category, global_percent: float) -> float:
    if product.markup_override is not None:
        return float(product.markup_override)
    if category is not None and category.markup_percent is not None:
        return float(category.markup_percent)
    return float(global_percent)


def charm_round(krw: float) -> int:
    """Round to the nearest 10 won, always slightly up (wholesale-friendly retail prices)."""
    import math

    return int(math.ceil(krw / 10.0)) * 10


def compute_sell_price(cost_krw: int, markup_percent: float) -> int:
    return charm_round(cost_krw * (1.0 + markup_percent / 100.0))


def apply_pricing(db, product) -> int:
    """Recompute product.price_sell from cost + effective markup. Returns new sell price."""
    from ..deps import get_setting

    global_pct = float(get_setting(db, "markup_percent", 35.0))
    return apply_pricing_with(product, global_pct)


def apply_pricing_with(product, global_pct: float) -> int:
    category = product.category
    pct = resolve_markup(product, category, global_pct)
    product.price_sell = compute_sell_price(product.price_cost, pct)
    return product.price_sell


def reapply_all(db, category_id: int | None = None) -> int:
    from .. import models

    q = db.query(models.Product)
    if category_id:
        q = q.filter(models.Product.category_id == category_id)
    from ..deps import get_setting

    global_pct = float(get_setting(db, "markup_percent", 35.0))
    count = 0
    for p in q.all():
        old = p.price_sell
        new = apply_pricing_with(p, global_pct)
        if old != new:
            count += 1
    db.commit()
    return count
