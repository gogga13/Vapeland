from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.utils import timezone

from .models import ProductDiscount, ProductVariant


DISCOUNT_RATE_3_THRESHOLD = Decimal("550.00")
DISCOUNT_RATE_5_THRESHOLD = Decimal("1050.00")
DISCOUNT_RATE_3 = Decimal("0.03")
DISCOUNT_RATE_5 = Decimal("0.05")
BIRTHDAY_BONUS = Decimal("150.00")
DEFAULT_VARIANT_NAME = "Стандарт"
CART_IMAGE_PLACEHOLDER = f"{settings.STATIC_URL}images/logo.png"


def money(value):
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def normalize_city(city):
    value = (city or "").strip().lower()
    replacements = ("м.", "м ", ".", ",")
    for item in replacements:
        value = value.replace(item, " ")
    return " ".join(value.split())


def is_mykolaiv(city):
    normalized = normalize_city(city)
    return any(name in normalized for name in ("миколаїв", "миколаев", "mykolaiv", "nikolaev"))


def is_birthday_bonus_available(birth_date, today=None):
    if not birth_date:
        return False

    if today is None:
        today = timezone.localtime().date()
    elif isinstance(today, datetime):
        today = timezone.localtime(today).date() if timezone.is_aware(today) else today.date()
    elif not isinstance(today, date):
        today = timezone.localtime().date()

    return birth_date.day == today.day and birth_date.month == today.month


def make_cart_key(product_id, variant_id=None):
    if variant_id:
        return f"{product_id}:{variant_id}"
    return str(product_id)


def parse_cart_key(raw_key):
    key = str(raw_key or "").strip()
    if ":" not in key:
        return key, None
    product_id, variant_id = key.split(":", 1)
    return product_id.strip(), variant_id.strip() or None


def get_tracked_stock(product, variant=None):
    if variant is not None and variant.stock_qty is not None:
        return int(variant.stock_qty)
    if product.stock_qty is not None:
        return int(product.stock_qty)
    return None


def is_stock_available(product, variant=None, quantity=1):
    tracked_stock = get_tracked_stock(product, variant)
    if tracked_stock is None:
        return True
    return quantity <= tracked_stock


def _coerce_at(at=None):
    at = at or timezone.localtime()
    if isinstance(at, datetime):
        if timezone.is_naive(at):
            return timezone.make_aware(at, timezone.get_current_timezone())
        return timezone.localtime(at)
    return timezone.localtime()


def get_active_product_discount_map(product_ids, at=None):
    product_ids = [int(product_id) for product_id in product_ids if product_id]
    if not product_ids:
        return {}

    at = _coerce_at(at)
    discounts = (
        ProductDiscount.objects.filter(
            product_id__in=product_ids,
            is_active=True,
            start_date__lte=at,
            end_date__gte=at,
        )
        .select_related("product")
        .order_by("product_id", "-start_date", "-id")
    )

    discount_map = {}
    for discount in discounts:
        if discount.product_id not in discount_map and discount.is_valid(at):
            discount_map[discount.product_id] = discount
    return discount_map


def calculate_product_discount_amount(base_price, discount):
    if not discount:
        return Decimal("0.00")

    base_price = money(base_price)
    if discount.discount_type == ProductDiscount.TYPE_PERCENT:
        discount_amount = money(base_price * (money(discount.value) / Decimal("100")))
    else:
        discount_amount = money(discount.value)
    return money(min(base_price, max(Decimal("0.00"), discount_amount)))


def build_product_discount_badge(discount):
    if not discount:
        return ""
    if discount.discount_type == ProductDiscount.TYPE_PERCENT:
        normalized = money(discount.value)
        if normalized == normalized.to_integral():
            return f"-{int(normalized)}%"
        return f"-{normalized.normalize()}%"
    return "АКЦІЯ"


def build_product_discount_label(discount):
    if not discount:
        return ""
    if discount.discount_type == ProductDiscount.TYPE_PERCENT:
        normalized = money(discount.value)
        if normalized == normalized.to_integral():
            return f"Знижка {int(normalized)}% на товар"
        return f"Знижка {normalized.normalize()}% на товар"
    return f"Акційна знижка {money(discount.value):.0f} грн"


def get_product_price_with_discount(product, user=None, at=None, product_discount=None):
    at = _coerce_at(at)
    discount = (
        product_discount
        if product_discount is not None
        else get_active_product_discount_map([product.pk], at=at).get(product.pk)
    )
    base_price = money(product.effective_price)
    discount_amount = calculate_product_discount_amount(base_price, discount)
    final_price = money(base_price - discount_amount)

    return {
        "base_price": base_price,
        "final_price": final_price,
        "discount_amount": discount_amount,
        "has_discount": discount_amount > 0,
        "discount_source": "product" if discount_amount > 0 else None,
        "discount_badge": build_product_discount_badge(discount),
        "discount_label": build_product_discount_label(discount),
        "discount_type": getattr(discount, "discount_type", ""),
        "discount_value": money(discount.value) if discount else Decimal("0.00"),
        "discount_end": discount.end_date if discount else None,
        "discount_object": discount,
    }


def enrich_products_with_discount_data(products, user=None, at=None):
    products = list(products)
    discount_map = get_active_product_discount_map([product.pk for product in products], at=at)
    for product in products:
        product.discount_data = get_product_price_with_discount(
            product,
            user=user,
            at=at,
            product_discount=discount_map.get(product.pk),
        )
    return products


def _resolve_cart_item_image_url(product, variant=None):
    if variant and getattr(variant, "image", None):
        return variant.image.url
    if product.image:
        return product.image.url

    first_variant = (
        product.variants.filter(is_active=True, image__isnull=False)
        .exclude(image="")
        .order_by("id")
        .first()
    )
    if first_variant and getattr(first_variant, "image", None):
        return first_variant.image.url
    return CART_IMAGE_PLACEHOLDER


def get_cart_items(cart):
    cart_items = []

    for raw_key, quantity in cart.items():
        product_id, variant_id = parse_cart_key(raw_key)

        try:
            from .models import Product

            product = Product.objects.select_related("category").get(id=int(product_id), is_active=True)
        except (Product.DoesNotExist, TypeError, ValueError):
            continue

        variant = None
        if variant_id:
            try:
                variant = ProductVariant.objects.get(id=int(variant_id), product=product, is_active=True)
            except (ProductVariant.DoesNotExist, TypeError, ValueError):
                continue

        quantity = int(quantity)
        tracked_stock = get_tracked_stock(product, variant)
        glycerin_price = money(product.effective_glycerin_price)
        original_unit_price = money(product.effective_price)
        original_total = money(original_unit_price * quantity)

        cart_items.append(
            {
                "cart_key": str(raw_key),
                "product": product,
                "variant": variant,
                "variant_name": variant.name if variant else DEFAULT_VARIANT_NAME,
                "image_url": _resolve_cart_item_image_url(product, variant),
                "quantity": quantity,
                "base_price": money(product.price),
                "glycerin_price": glycerin_price,
                "original_unit_price": original_unit_price,
                "original_total": original_total,
                "unit_price": original_unit_price,
                "total": original_total,
                "discount_amount": Decimal("0.00"),
                "discount_source": None,
                "discount_label": "",
                "discount_badge": "",
                "has_discount": False,
                "display_old_price": None,
                "extra": "Гліцерин" if glycerin_price > 0 else "",
                "tracked_stock": tracked_stock,
                "stock_limited": tracked_stock is not None,
                "is_available": tracked_stock is None or quantity <= tracked_stock,
            }
        )

    return cart_items


def _apply_item_discount(item, line_discount, source, label="", badge=""):
    line_discount = money(max(Decimal("0.00"), line_discount))
    original_total = money(item["original_total"])
    quantity = max(1, int(item["quantity"]))
    final_total = money(max(Decimal("0.00"), original_total - line_discount))
    final_unit_price = money(final_total / Decimal(quantity))

    item["unit_price"] = final_unit_price
    item["total"] = final_total
    item["discount_amount"] = line_discount
    item["discount_source"] = source
    item["discount_label"] = label
    item["discount_badge"] = badge
    item["has_discount"] = line_discount > 0
    item["display_old_price"] = item["original_unit_price"] if line_discount > 0 else None


def _extract_birth_date(user):
    if not user or not getattr(user, "is_authenticated", False):
        return None
    profile = getattr(user, "profile", None)
    return getattr(profile, "birth_date", None) if profile else None


def calculate_cart_total(cart, user=None, city="", birthday_bonus_selected=False, birthday_bonus_allowed=None):
    cart_items = get_cart_items(cart) if isinstance(cart, dict) else list(cart)
    at = _coerce_at()
    birth_date = _extract_birth_date(user)
    if birthday_bonus_allowed is None:
        birthday_bonus_allowed = is_birthday_bonus_available(birth_date, today=at)

    for item in cart_items:
        item["unit_price"] = money(item["original_unit_price"])
        item["total"] = money(item["original_total"])
        item["discount_amount"] = Decimal("0.00")
        item["discount_source"] = None
        item["discount_label"] = ""
        item["discount_badge"] = ""
        item["has_discount"] = False
        item["display_old_price"] = None

    subtotal = money(sum((item["original_total"] for item in cart_items), Decimal("0.00")))
    product_discount_map = get_active_product_discount_map([item["product"].pk for item in cart_items], at=at)

    product_discount_total = Decimal("0.00")
    for item in cart_items:
        pricing = get_product_price_with_discount(
            item["product"],
            user=user,
            at=at,
            product_discount=product_discount_map.get(item["product"].pk),
        )
        item["product_discount"] = pricing
        if pricing["has_discount"]:
            line_discount = money(pricing["discount_amount"] * item["quantity"])
            _apply_item_discount(
                item,
                line_discount,
                source="product",
                label=pricing["discount_label"],
                badge=pricing["discount_badge"],
            )
            product_discount_total += line_discount

    if subtotal >= DISCOUNT_RATE_5_THRESHOLD:
        percent_rate = DISCOUNT_RATE_5
        percent_label = "Знижка 5% на чек"
    elif subtotal >= DISCOUNT_RATE_3_THRESHOLD:
        percent_rate = DISCOUNT_RATE_3
        percent_label = "Знижка 3% на чек"
    else:
        percent_rate = Decimal("0.00")
        percent_label = "Знижка за сумою не застосовується"

    percent_discount = Decimal("0.00")
    if percent_rate > 0:
        for item in cart_items:
            if item["discount_source"]:
                continue
            line_discount = money(item["original_total"] * percent_rate)
            _apply_item_discount(item, line_discount, source="cart", label=percent_label)
            percent_discount += line_discount

    birthday_bonus_selected = bool(birthday_bonus_selected and birthday_bonus_allowed)
    birthday_discount = Decimal("0.00")
    birthday_candidates = [item for item in cart_items if not item["discount_source"]]
    if birthday_bonus_selected and birthday_candidates:
        eligible_total = money(sum((item["original_total"] for item in birthday_candidates), Decimal("0.00")))
        if eligible_total > 0:
            birthday_pool = money(min(BIRTHDAY_BONUS, eligible_total))
            remaining_pool = birthday_pool
            for index, item in enumerate(birthday_candidates, start=1):
                if index == len(birthday_candidates):
                    line_discount = remaining_pool
                else:
                    ratio_discount = (birthday_pool * item["original_total"]) / eligible_total
                    line_discount = money(ratio_discount)
                    line_discount = money(min(line_discount, remaining_pool))
                remaining_pool = money(remaining_pool - line_discount)
                _apply_item_discount(item, line_discount, source="birthday", label="Бонус до дня народження")
                birthday_discount += line_discount

    product_discount_total = money(product_discount_total)
    percent_discount = money(percent_discount)
    birthday_discount = money(birthday_discount)
    total_discount = money(product_discount_total + percent_discount + birthday_discount)
    final_total = money(sum((item["total"] for item in cart_items), Decimal("0.00")))

    city_is_mykolaiv = is_mykolaiv(city)
    delivery_is_free = city_is_mykolaiv or subtotal >= DISCOUNT_RATE_5_THRESHOLD
    if city_is_mykolaiv:
        delivery_label = "Безкоштовна доставка по м. Миколаїв"
    elif subtotal >= DISCOUNT_RATE_5_THRESHOLD:
        delivery_label = "Безкоштовна доставка по Україні"
    else:
        delivery_label = "Доставка за тарифами перевізника"

    return {
        "items": cart_items,
        "subtotal": subtotal,
        "product_discount_total": product_discount_total,
        "percent_rate": percent_rate,
        "percent_discount": percent_discount,
        "percent_label": percent_label,
        "birthday_discount": birthday_discount,
        "birthday_bonus_allowed": birthday_bonus_allowed,
        "birthday_bonus_selected": birthday_bonus_selected,
        "birthday_verification_required": birthday_bonus_selected,
        "total_discount": total_discount,
        "final_total": final_total,
        "delivery_is_free": delivery_is_free,
        "delivery_label": delivery_label,
        "city_is_mykolaiv": city_is_mykolaiv,
    }


def calculate_cart_summary(cart_items, city="", birthday_bonus_selected=False, birthday_bonus_allowed=False, user=None):
    return calculate_cart_total(
        cart_items,
        user=user,
        city=city,
        birthday_bonus_selected=birthday_bonus_selected,
        birthday_bonus_allowed=birthday_bonus_allowed,
    )
