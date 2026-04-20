from django.conf import settings

from .pricing import calculate_cart_summary, get_cart_items


def cart_processor(request):
    cart = request.session.get("cart", {})
    cart_items = get_cart_items(cart)
    city = ""
    if getattr(request, "user", None) and request.user.is_authenticated and hasattr(request.user, "profile"):
        city = request.user.profile.city or ""

    cart_summary = calculate_cart_summary(
        cart_items,
        city=city,
        birthday_bonus_selected=False,
        user=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
    )

    return {
        "cart_count": sum(item["quantity"] for item in cart_items) if cart_items else 0,
        "cart_total": cart_summary["final_total"],
        "cart_products": cart_summary["items"],
        "cart_summary": cart_summary,
    }


def support_processor(request):
    raw_phone = getattr(settings, "SUPPORT_PHONE", "").strip()
    phone_href = "".join(char for char in raw_phone if char.isdigit() or char == "+")

    return {
        "support_telegram_url": getattr(settings, "SUPPORT_TELEGRAM_URL", "").strip(),
        "support_instagram_url": getattr(settings, "SUPPORT_INSTAGRAM_URL", "").strip(),
        "support_phone": raw_phone,
        "support_phone_href": phone_href,
    }
