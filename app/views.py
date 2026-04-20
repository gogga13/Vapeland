import logging
import random
import re
from datetime import timedelta

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST

from app_web.email_utils import send_reset_code
from app_web.forms import PasswordResetConfirmForm, PasswordResetRequestForm, ProfileForm, ReviewForm
from app_web.models import (
    Brand,
    Category,
    Order,
    OrderItem,
    PasswordResetCode,
    Product,
    ProductDiscount,
    ProductVariant,
    Profile,
    Review,
)
from app_web.pricing import (
    DEFAULT_VARIANT_NAME,
    calculate_cart_summary,
    enrich_products_with_discount_data,
    get_cart_items,
    get_tracked_stock,
    is_birthday_bonus_available,
    make_cart_key,
)


User = get_user_model()
STATIC_IMAGE_FALLBACK = f"{settings.STATIC_URL}images/logo.png"
logger = logging.getLogger(__name__)


CATALOG_ICON_SVGS = {
    "pod": """
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="3" y="4" width="5" height="16" rx="1.5"></rect>
            <line x1="5.5" y1="7" x2="5.5" y2="17"></line>
            <rect x="12.5" y="3" width="8.5" height="18" rx="2"></rect>
            <line x1="16.75" y1="6" x2="16.75" y2="17"></line>
            <line x1="14.5" y1="19" x2="19" y2="19"></line>
        </svg>
    """,
    "cartridge": """
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M6 6h4v10H6z"></path>
            <path d="M7.5 3.5h1"></path>
            <path d="M14 8h4v8h-4z"></path>
            <path d="M15.5 5.5h1"></path>
            <path d="M9 13h6"></path>
            <path d="M4 19h16"></path>
        </svg>
    """,
    "liquid": """
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M7 8h4v11H7z"></path>
            <path d="M8 4h2v3H8z"></path>
            <path d="M15 10h4v9h-4z"></path>
            <path d="M16 6h2v3h-2z"></path>
            <path d="M9 13.5c0 .9-.5 1.5-1 1.5s-1-.6-1-1.5.5-1.5 1-1.5 1 .6 1 1.5z"></path>
            <path d="M17 14.5c0 .9-.5 1.5-1 1.5s-1-.6-1-1.5.5-1.5 1-1.5 1 .6 1 1.5z"></path>
        </svg>
    """,
    "disposable": """
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="4" y="5" width="6" height="15" rx="1.5"></rect>
            <rect x="14" y="4" width="6" height="16" rx="1.5"></rect>
            <line x1="7" y1="8" x2="7" y2="17"></line>
            <line x1="17" y1="7" x2="17" y2="17"></line>
            <line x1="5" y1="20" x2="9" y2="20"></line>
            <line x1="15" y1="20" x2="19" y2="20"></line>
        </svg>
    """,
    "default": """
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M4 19h16"></path>
            <path d="M6 16l3-9 3 6 3-8 3 11"></path>
        </svg>
    """,
}


CATALOG_PRESETS = {
    "pod system": {
        "label": "POD-системи",
        "icon": "pod",
        "featured_group_title": "Багаторазові POD-системи",
        "featured_list_title": "Популярні POD-системи",
        "brands_group_title": "POD-моди",
        "brands_list_title": "Популярні бренди POD-систем",
        "quick_links": [
            "Картриджі та випаровувачі для POD-систем",
            "RBA, RBK та 510 адаптери для POD-систем",
        ],
        "brand_fallbacks": ["Vaporesso", "OXVA", "Lost Vape", "Geekvape", "Voopoo", "Smok", "Uwell", "Smoant", "Nevoks", "Aspire"],
    },
    "cartridge": {
        "label": "Картриджі та випаровувачі для POD-систем",
        "icon": "cartridge",
        "featured_group_title": "Картриджі та змінні елементи",
        "featured_list_title": "Популярні картриджі",
        "brands_group_title": "Сумісні лінійки",
        "brands_list_title": "Популярні бренди",
        "quick_links": [
            "Картриджі для Vaporesso XROS",
            "Випаровувачі та змінні комплектуючі",
        ],
        "brand_fallbacks": ["Vaporesso XROS", "Voopoo Argus", "OXVA XLIM", "Lost Vape Ursa", "Geekvape Wenax"],
    },
    "liquids": {
        "label": "Рідини для електронних сигарет",
        "icon": "liquid",
        "featured_group_title": "Рідини для щоденного використання",
        "featured_list_title": "Популярні смаки",
        "brands_group_title": "Сольові та органічні рідини",
        "brands_list_title": "Популярні бренди рідин",
        "quick_links": [
            "Сольові рідини для POD-систем",
            "Органічні рідини та нові лінійки смаків",
        ],
        "brand_fallbacks": ["Chaser", "In Bottle", "Hype", "Lucky Salt", "Octolab", "Twisted", "Balon"],
    },
    "disposables": {
        "label": "Електронні сигарети",
        "icon": "disposable",
        "featured_group_title": "Одноразові електронні сигарети",
        "featured_list_title": "Популярні моделі",
        "brands_group_title": "Компактні рішення",
        "brands_list_title": "Популярні бренди одноразок",
        "quick_links": [
            "Одноразові електронні сигарети на кожен день",
            "Преміальні лінійки та новинки",
        ],
        "brand_fallbacks": ["Lost Mary", "Elf Bar", "Vozol", "Maskking", "HQD", "RandM"],
    },
}


def unique_items(values):
    result = []
    seen = set()
    for value in values:
        normalized = (value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def category_product_filter(category):
    return Q(category=category) | Q(subcategory__parent=category) | Q(category__parent=category)


def subcategory_product_filter(subcategory):
    return Q(subcategory=subcategory) | Q(category=subcategory)


def brand_product_filter(brand):
    return Q(brand_ref=brand) | Q(brand__iexact=brand.name)


def get_product_top_category(product):
    category = getattr(product, "category", None)
    if not category:
        return None
    return category.parent if getattr(category, "parent_id", None) else category


def get_product_subcategory(product):
    if getattr(product, "subcategory_id", None):
        return product.subcategory

    category = getattr(product, "category", None)
    if category and getattr(category, "parent_id", None):
        return category
    return None


def attach_product_taxonomy(products):
    for product in products:
        product.catalog_category = get_product_top_category(product)
        product.catalog_subcategory = get_product_subcategory(product)
        product.catalog_brand_name = getattr(product, "display_brand", "") or (product.brand or "").strip()


def normalize_spec_number(value):
    normalized = str(value or "").replace(",", ".").strip()
    if normalized.endswith(".0"):
        normalized = normalized[:-2]
    return normalized


def normalize_spec_label(value):
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("'", "ʼ")
        .replace("`", "ʼ")
    )


def first_spec_match(text, patterns, formatter=None):
    if not text:
        return ""

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        if formatter:
            return formatter(match)
        if match.lastindex:
            return (match.group(1) or "").strip()
        return (match.group(0) or "").strip()
    return ""


def build_product_specs(product):
    catalog_category = getattr(product, "catalog_category", None) or getattr(product, "category", None)
    manual_specs = []
    manual_labels = set()
    for spec in product.specifications.all():
        label = (spec.label or "").strip()
        value = (spec.value or "").strip()
        if not label or not value:
            continue
        manual_specs.append(
            {
                "label": label,
                "value": value,
                "is_accent": bool(spec.is_highlight),
            }
        )
        manual_labels.add(normalize_spec_label(label))

    text = "\n".join(
        part.strip()
        for part in [
            getattr(product, "name", "") or "",
            getattr(product, "description", "") or "",
            getattr(product, "display_brand", "") or "",
        ]
        if part and part.strip()
    )
    lowered = text.lower()

    volume = first_spec_match(
        text,
        [r"(\d+(?:[.,]\d+)?)\s*(?:мл|ml)\b"],
        lambda match: f"{normalize_spec_number(match.group(1))} мл",
    )
    strength = first_spec_match(
        text,
        [
            r"(\d+(?:[.,]\d+)?)\s*(?:мг|mg)\b",
            r"(\d+(?:[.,]\d+)?)\s*%",
        ],
        lambda match: f"{normalize_spec_number(match.group(1))} {'мг' if 'м' in match.group(0).lower() else '%'}",
    )
    vg_pg = first_spec_match(
        text,
        [r"\b(\d{2}\s*/\s*\d{2})\b"],
        lambda match: match.group(1).replace(" ", ""),
    )

    type_value = ""
    type_map = [
        (r"\bсольов\w*\b", "сольовий"),
        (r"\borganic\b|\bорган[іi]ч\w*\b", "органічний"),
        (r"\bfree\s*base\b|\bfreebase\b|\bкласичн\w*\b", "класичний"),
        (r"\baroma\b|\bароматизатор\w*\b", "ароматизатор"),
    ]
    for pattern, label in type_map:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            type_value = label
            break

    country_value = ""
    country_map = [
        ("україна", "Україна"),
        ("ukraine", "Україна"),
        ("польща", "Польща"),
        ("poland", "Польща"),
        ("китай", "Китай"),
        ("china", "Китай"),
        ("малайзія", "Малайзія"),
        ("malaysia", "Малайзія"),
        ("сша", "США"),
        ("usa", "США"),
        ("америка", "США"),
        ("велика британія", "Великобританія"),
        ("uk", "Великобританія"),
        ("британія", "Великобританія"),
    ]
    for needle, label in country_map:
        if needle in lowered:
            country_value = label
            break

    specs = list(manual_specs)
    if volume:
        if normalize_spec_label("Обʼєм") not in manual_labels:
            specs.append({"label": "Обʼєм", "value": volume})
    if strength:
        if normalize_spec_label("Міцність") not in manual_labels:
            specs.append({"label": "Міцність", "value": strength})
    if vg_pg:
        if normalize_spec_label("VG/PG") not in manual_labels:
            specs.append({"label": "VG/PG", "value": vg_pg})
    if type_value:
        if normalize_spec_label("Тип") not in manual_labels:
            specs.append({"label": "Тип", "value": type_value})
    if getattr(product, "display_brand", ""):
        if normalize_spec_label("Бренд") not in manual_labels:
            specs.append({"label": "Бренд", "value": product.display_brand})
    if country_value:
        if normalize_spec_label("Країна") not in manual_labels:
            specs.append({"label": "Країна", "value": country_value})
    if catalog_category:
        if normalize_spec_label("Категорія") not in manual_labels:
            specs.append({"label": "Категорія", "value": catalog_category.name})
    if getattr(product, "includes_glycerin", False) and getattr(product, "effective_glycerin_price", 0) > 0:
        if normalize_spec_label("У комплекті") not in manual_labels:
            specs.append(
                {
                    "label": "У комплекті",
                    "value": f"гліцерин (+{product.effective_glycerin_price:.0f} грн)",
                    "is_accent": True,
                }
            )
    return specs


def build_catalog_menu():
    categories = list(Category.objects.filter(parent__isnull=True).order_by("name"))
    products = list(Product.objects.filter(is_active=True).select_related("category").order_by("id"))
    menu = []

    for category in categories:
        preset = CATALOG_PRESETS.get(category.name.lower().strip(), {})
        category_products = [
            product for product in products if product.category_id == category.id or product.category.parent_id == category.id
        ]

        featured_links = [
            {"label": product.name, "url": reverse("product_detail", args=[product.slug])}
            for product in category_products[:8]
        ]
        if not featured_links:
            featured_links = [{"label": "Товари скоро з’являться", "url": reverse("catalog_page") + f"?category={category.id}"}]

        brand_links = [
            {"label": brand, "url": reverse("catalog_page") + f"?category={category.id}"}
            for brand in unique_items([product.brand for product in category_products] + preset.get("brand_fallbacks", []))[:10]
        ]

        quick_links = [
            {"label": label, "url": reverse("catalog_page") + f"?category={category.id}"}
            for label in preset.get("quick_links", [])
        ]

        menu.append(
            {
                "key": f"catalog-category-{category.id}",
                "label": preset.get("label", category.name),
                "icon_svg": mark_safe(CATALOG_ICON_SVGS.get(preset.get("icon", "default"), CATALOG_ICON_SVGS["default"])),
                "featured_group_title": preset.get("featured_group_title", category.name),
                "featured_list_title": preset.get("featured_list_title", "Популярні товари"),
                "featured_links": featured_links,
                "brands_group_title": preset.get("brands_group_title", "Популярні бренди"),
                "brands_list_title": preset.get("brands_list_title", "Бренди категорії"),
                "brand_links": brand_links,
                "quick_links": quick_links,
            }
        )

    return menu


def get_category_image_url(category):
    if category.image:
        return category.image.url

    category_products = Product.objects.filter(
        Q(category=category) | Q(category__parent=category),
        is_active=True,
        image__isnull=False,
    ).exclude(image="")
    first_product = category_products.first()
    if first_product and first_product.image:
        return first_product.image.url

    variant_image = (
        ProductVariant.objects.filter(
            Q(product__category=category) | Q(product__category__parent=category),
            product__is_active=True,
            is_active=True,
            image__isnull=False,
        )
        .exclude(image="")
        .order_by("product_id", "id")
        .first()
    )
    if variant_image and variant_image.image:
        return variant_image.image.url

    return STATIC_IMAGE_FALLBACK


def get_product_primary_image_url(product, variants_queryset=None):
    if getattr(product, "image", None):
        return product.image.url

    variants = variants_queryset
    if variants is None:
        variants = product.variants.filter(is_active=True)

    variant_image = variants.filter(image__isnull=False).exclude(image="").first()
    if variant_image and getattr(variant_image, "image", None):
        return variant_image.image.url

    return STATIC_IMAGE_FALLBACK


def build_featured_categories():
    featured_categories = (
        Category.objects.filter(is_featured=True, parent__isnull=True)
        .prefetch_related("children")
        .order_by("name")[:4]
    )

    result = []
    for category in featured_categories:
        child_names = list(category.children.order_by("name").values_list("name", flat=True)[:4])
        if not child_names:
            child_names = list(
                Product.objects.filter(Q(category=category) | Q(category__parent=category), is_active=True)
                .order_by("name")
                .values_list("name", flat=True)[:4]
            )

        result.append(
            {
                "id": category.id,
                "name": category.name,
                "image_url": get_category_image_url(category),
                "items": child_names,
                "url": f"{reverse('catalog_page')}?category={category.id}",
            }
        )

    return result


def send_telegram_message(text):
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return None

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        response = requests.post(url, data=payload, timeout=settings.TELEGRAM_API_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        logger.warning("Telegram send error: %s", exc)
        return None


def build_order_telegram_text(order):
    lines = [
        f"📦 Нове замовлення #{order.id}",
        "",
        f"👤 Клієнт: {order.first_name} {order.last_name}".strip(),
        f"📞 Телефон: {order.phone}",
        "",
        "🚚 Доставка:",
        f"{order.city}, {order.address}",
        "",
        "📋 Товари:",
    ]

    for item in order.items.all():
        item_lines = [
            "",
            f"* {item.product_name}",
            f"  Варіант: {item.variant_name}",
            f"  Кількість: {item.quantity}",
        ]
        if item.glycerin_price > 0:
            item_lines.append(f"  Гліцерин: включено ({item.glycerin_price:.0f} грн)")
        item_lines.append(f"  Ціна: {item.line_total:.0f} грн")
        lines.extend(item_lines)


    lines.extend(
        [
            "",
            "💰 Ітого:",
            f"Сума: {order.subtotal_price:.0f} грн",
            f"Знижка: {order.discount_amount:.0f} грн",
            f"До оплати: {order.total_price:.0f} грн",
        ]
    )

    if order.birthday_verification_required:
        lines.append("🎂 Потрібна перевірка документів по бонусу до дня народження")

    return "\n".join(lines)


def home(request):
    approved_site_reviews = Review.objects.filter(product__isnull=True, is_approved=True).select_related("user")
    site_review_stats = approved_site_reviews.aggregate(avg=Avg("rating"), count=Count("id"))
    now = timezone.localtime()
    discounted_products = list(
        Product.objects.filter(
            is_active=True,
            product_discounts__is_active=True,
            product_discounts__start_date__lte=now,
            product_discounts__end_date__gte=now,
        )
        .select_related("category")
        .distinct()
        .order_by("name")[:8]
    )
    enrich_products_with_discount_data(discounted_products, user=request.user if request.user.is_authenticated else None, at=now)
    _attach_card_image_urls(discounted_products)

    return render(
        request,
        "index.html",
        {
            "popular_categories": build_featured_categories(),
            "discounted_products": discounted_products,
            "site_reviews": approved_site_reviews[:6],
            "site_rating_average": site_review_stats["avg"] or 0,
            "site_reviews_count": site_review_stats["count"] or 0,
            "site_review_form": ReviewForm(prefix="site"),
        },
    )


def _attach_card_image_urls(products):
    products = [p for p in (products or []) if p]
    if not products:
        return

    variant_images = (
        ProductVariant.objects.filter(
            product__in=products,
            is_active=True,
            image__isnull=False,
        )
        .exclude(image="")
        .order_by("product_id", "id")
        .only("product_id", "image")
    )
    first_variant_image_by_product = {}
    for variant in variant_images:
        if variant.product_id not in first_variant_image_by_product and variant.image:
            first_variant_image_by_product[variant.product_id] = variant.image.url

    for product in products:
        if product.image:
            product.card_image_url = product.image.url
        else:
            variant_image = first_variant_image_by_product.get(product.id)
            product.card_image_url = variant_image or STATIC_IMAGE_FALLBACK


def catalog_page(request):
    categories = list(Category.objects.filter(parent__isnull=True).prefetch_related("children").order_by("name"))
    products = (
        Product.objects.filter(is_active=True)
        .select_related("category", "subcategory", "brand_ref")
        .annotate(active_variant_count=Count("variants", filter=Q(variants__is_active=True), distinct=True))
        .order_by("name")
    )

    selected_category = None
    selected_subcategory = None
    selected_brand = None
    query = request.GET.get("q", "").strip()
    category_id = request.GET.get("category", "").strip()
    subcategory_id = request.GET.get("subcategory", "").strip()
    brand_slug = request.GET.get("brand", "").strip()
    search_filter = Q()

    if query:
        search_filter = (
            Q(name__icontains=query)
            | Q(brand__icontains=query)
            | Q(brand_ref__name__icontains=query)
            | Q(sku__icontains=query)
            | Q(description__icontains=query)
        )

    if category_id.isdigit():
        selected_category = next((category for category in categories if category.id == int(category_id)), None)
        if selected_category:
            products = products.filter(category_product_filter(selected_category))

    if subcategory_id.isdigit():
        selected_subcategory = Category.objects.select_related("parent").filter(pk=int(subcategory_id), parent__isnull=False).first()
        if selected_subcategory:
            selected_category = selected_subcategory.parent
            products = products.filter(subcategory_product_filter(selected_subcategory))

    if query:
        products = products.filter(search_filter)

    brand_scope = products
    if brand_slug:
        if brand_slug.isdigit():
            selected_brand = Brand.objects.filter(pk=int(brand_slug)).first()
        else:
            selected_brand = Brand.objects.filter(slug=brand_slug).first()
        if selected_brand:
            products = products.filter(brand_product_filter(selected_brand))

    paginator = Paginator(products.distinct(), 24)
    page_obj = paginator.get_page(request.GET.get("page") or 1)
    page_products = list(page_obj.object_list)
    enrich_products_with_discount_data(page_products, user=request.user if request.user.is_authenticated else None)
    _attach_card_image_urls(page_products)
    attach_product_taxonomy(page_products)

    sidebar_brands = list(
        Brand.objects.filter(products__in=brand_scope)
        .order_by("name")
        .distinct()
    )
    selected_brand_category_ids = set(selected_brand.categories.values_list("id", flat=True)) if selected_brand else set()
    for category in categories:
        nested_products = list(
            Product.objects.filter(is_active=True)
            .filter(category_product_filter(category))
            .filter(search_filter)
            .select_related("category", "subcategory", "brand_ref")
            .order_by("name")
        )
        attach_product_taxonomy(nested_products)

        child_map = {}
        brand_map = {}
        for nested_product in nested_products:
            if nested_product.catalog_subcategory:
                child_map[nested_product.catalog_subcategory.id] = nested_product.catalog_subcategory
            if nested_product.brand_ref_id and nested_product.brand_ref:
                brand_map[nested_product.brand_ref.id] = nested_product.brand_ref

        category.sidebar_children = sorted(child_map.values(), key=lambda item: item.name.lower())
        child_names = {child.name.casefold() for child in category.sidebar_children}
        category.sidebar_brands = [
            brand
            for brand in sorted(brand_map.values(), key=lambda item: item.name.lower())
            if brand.name.casefold() not in child_names
        ]
        category.sidebar_has_nested = bool(category.sidebar_children or category.sidebar_brands)
        category.sidebar_open = bool(
            (selected_category and selected_category.id == category.id)
            or (selected_subcategory and selected_subcategory.parent_id == category.id)
            or category.id in selected_brand_category_ids
        )

    page_title = "Усі товари"
    if selected_subcategory:
        page_title = selected_subcategory.name
    elif selected_brand:
        page_title = selected_brand.name
    elif selected_category:
        page_title = selected_category.name

    page_description = (
        f"Показані товари за запитом \"{query}\"."
        if query
        else "Обирайте актуальні позиції VapeLand і переходьте до потрібної категорії, підкатегорії або бренду без зайвих кроків."
    )

    return render(
        request,
        "catalog.html",
        {
            "categories": categories,
            "products": page_products,
            "page_obj": page_obj,
            "selected_category": selected_category,
            "selected_subcategory": selected_subcategory,
            "selected_brand": selected_brand,
            "sidebar_brands": sidebar_brands,
            "search_query": query,
            "products_total": paginator.count,
            "page_title": page_title,
            "page_description": page_description,
        },
    )


def search_products(request):
    query = request.GET.get("q", "").strip()
    if len(query) < 2:
        return JsonResponse({"results": []})

    products = list(
        Product.objects.filter(is_active=True)
        .filter(
            Q(name__icontains=query)
            | Q(brand__icontains=query)
            | Q(brand_ref__name__icontains=query)
            | Q(sku__icontains=query)
            | Q(description__icontains=query)
        )
        .select_related("category", "subcategory", "brand_ref")
        .order_by("name")[:8]
    )
    enrich_products_with_discount_data(products, user=request.user if request.user.is_authenticated else None)
    attach_product_taxonomy(products)

    results = []
    for product in products:
        results.append(
            {
                "id": product.id,
                "name": product.name,
                "price": float(product.discount_data["final_price"]),
                "image": get_product_primary_image_url(product),
                "url": reverse("product_detail", args=[product.slug]),
            }
        )

    return JsonResponse({"results": results})


def discounts_page(request):
    return render(request, "discounts.html")


def age_restrictions_page(request):
    return render(request, "age_restrictions.html", {"disable_age_gate": True})


def responsible_consumption_page(request):
    return render(request, "responsible_consumption.html", {"disable_age_gate": True})
def _nova_poshta_request(called_method, method_properties):
    api_key = getattr(settings, "NOVA_POSHTA_API_KEY", "")
    if not api_key:
        return []

    try:
        response = requests.post(
            "https://api.novaposhta.ua/v2.0/json/",
            json={
                "apiKey": api_key,
                "modelName": "Address",
                "calledMethod": called_method,
                "methodProperties": method_properties,
            },
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException:
        return []

    if not payload.get("success"):
        return []

    return payload.get("data", [])


@login_required
def search_np_cities(request):
    query = request.GET.get("q", "").strip()
    if len(query) < 2:
        return JsonResponse({"results": []})

    cities = _nova_poshta_request("getCities", {"FindByString": query, "Limit": "10"})
    results = []
    for city in cities:
        name = city.get("Description") or city.get("Present")
        ref = city.get("Ref")
        if name and ref:
            meta_parts = [
                city.get("SettlementTypeDescription"),
                city.get("AreaDescription"),
            ]
            meta = " • ".join(part.strip() for part in meta_parts if part and part.strip())
            results.append({"name": name, "ref": ref, "meta": meta})

    return JsonResponse({"results": results})


@login_required
def search_np_warehouses(request):
    city_ref = request.GET.get("city_ref", "").strip()
    query = request.GET.get("q", "").strip()
    if not city_ref:
        return JsonResponse({"results": []})

    warehouses = _nova_poshta_request(
        "getWarehouses",
        {
            "CityRef": city_ref,
            "FindByString": query,
            "Limit": "20",
        },
    )
    results = []
    for warehouse in warehouses:
        name = warehouse.get("Description") or warehouse.get("ShortAddress")
        if name:
            meta_parts = [
                warehouse.get("CategoryOfWarehouse"),
                warehouse.get("ShortAddress"),
            ]
            meta = " • ".join(part.strip() for part in meta_parts if part and part.strip() and part.strip() != name.strip())
            results.append({"name": name, "meta": meta})

    return JsonResponse({"results": results})


@login_required
def profile(request):
    profile_obj, _ = Profile.objects.get_or_create(user=request.user)
    form = ProfileForm(request.POST or None, instance=profile_obj, user=request.user)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Профіль оновлено.")
        return redirect("profile")

    return render(request, "profile.html", {"form": form})



@login_required
def orders_page(request):
    orders = Order.objects.filter(user=request.user).prefetch_related("items").order_by("-created_at")
    return render(request, "orders.html", {"orders": orders})

@staff_member_required
def order_api_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related("user").prefetch_related("items"),
        pk=order_id,
    )

    customer_name = f"{order.first_name} {order.last_name}".strip()
    customer_email = order.user.email if order.user_id and order.user and order.user.email else ""
    customer_address = ", ".join(part for part in [order.city, order.address] if part)

    items = []
    for item in order.items.all():
        items.append(
            {
                "productId": item.product_id,
                "name": item.product_name,
                "variantName": item.variant_name,
                "extra": item.extra,
                "price": float(item.price),
                "quantity": item.quantity,
                "lineTotal": float(item.line_total),
            }
        )

    return JsonResponse(
        {
            "id": order.id,
            "createdAt": timezone.localtime(order.created_at).isoformat(),
            "status": order.status,
            "customer": {
                "name": customer_name,
                "phone": order.phone,
                "email": customer_email,
                "address": customer_address,
            },
            "items": items,
            "totalPrice": float(order.total_price),
            "comment": order.comment or "",
        }
    )


def verify_page(request):
    messages.info(request, "Додаткова верифікація не потрібна. Ви вже можете користуватися акаунтом.")
    return redirect("profile")


@require_POST
def add_to_cart(request, product_id):
    cart = request.session.get("cart", {})
    variant_id = request.POST.get("variant_id")

    product = get_object_or_404(Product, id=product_id, is_active=True)
    variant = None
    if variant_id:
        variant = get_object_or_404(ProductVariant, id=variant_id, product=product, is_active=True)
    elif product.variants.filter(is_active=True).exists():
        return JsonResponse({"status": "error", "message": "Оберіть варіант товару."}, status=400)

    cart_key = make_cart_key(product.id, variant.id if variant else None)
    current_quantity = int(cart.get(cart_key, 0))
    tracked_stock = get_tracked_stock(product, variant)
    if tracked_stock is not None and current_quantity + 1 > tracked_stock:
        return JsonResponse({"status": "error", "message": "Товару немає в достатній кількості."}, status=400)

    cart[cart_key] = current_quantity + 1

    request.session["cart"] = cart
    cart_items = get_cart_items(cart)
    cart_count = sum(item["quantity"] for item in cart_items)
    return JsonResponse({"status": "ok", "cart_count": cart_count})


def cart_detail(request):
    cart = request.session.get("cart", {})
    cart_items = get_cart_items(cart)
    customer_city = ""
    if request.user.is_authenticated:
        profile_obj, _ = Profile.objects.get_or_create(user=request.user)
        customer_city = profile_obj.city or ""

    pricing = calculate_cart_summary(
        cart_items,
        city=customer_city,
        birthday_bonus_selected=False,
        user=request.user if request.user.is_authenticated else None,
    )
    return render(request, "cart.html", {"cart_items": pricing["items"], "pricing": pricing})


@require_POST
def cart_update(request):
    cart = request.session.get("cart", {})
    cart_key = request.POST.get("cart_key", "").strip()
    quantity_raw = request.POST.get("quantity", "1").strip()

    if cart_key not in cart:
        return redirect("cart_detail")

    try:
        quantity = int(quantity_raw)
    except (TypeError, ValueError):
        quantity = 1

    if quantity <= 0:
        cart.pop(cart_key, None)
        request.session["cart"] = cart
        return redirect("cart_detail")

    product_id, variant_id = cart_key.split(":", 1) if ":" in cart_key else (cart_key, None)
    try:
        product = Product.objects.get(pk=int(product_id), is_active=True)
    except (Product.DoesNotExist, TypeError, ValueError):
        cart.pop(cart_key, None)
        request.session["cart"] = cart
        return redirect("cart_detail")

    variant = None
    if variant_id:
        try:
            variant = ProductVariant.objects.get(pk=int(variant_id), product=product, is_active=True)
        except (ProductVariant.DoesNotExist, TypeError, ValueError):
            variant = None

    tracked_stock = get_tracked_stock(product, variant)
    if tracked_stock is not None and quantity > tracked_stock:
        messages.error(request, "Товару немає в достатній кількості.")
        cart[cart_key] = tracked_stock
    else:
        cart[cart_key] = quantity

    request.session["cart"] = cart
    return redirect("cart_detail")


@require_POST
def cart_remove(request):
    cart = request.session.get("cart", {})
    cart_key = request.POST.get("cart_key", "").strip()
    if cart_key in cart:
        cart.pop(cart_key, None)
        request.session["cart"] = cart
    return redirect("cart_detail")

@require_POST
def cart_clear(request):
    if "cart" in request.session:
        del request.session["cart"]
    return redirect("cart_detail")


@login_required
def checkout(request):
    if not request.session.get("cart"):
        return redirect("home")

    profile_obj, _ = Profile.objects.get_or_create(user=request.user)
    cart_items = get_cart_items(request.session.get("cart", {}))
    if any(not item["is_available"] for item in cart_items):
        messages.error(request, "У кошику є товари з недостатнім залишком. Перевірте кошик перед оформленням.")
        return redirect("cart_detail")

    birthday_bonus_allowed = is_birthday_bonus_available(profile_obj.birth_date)
    pricing = calculate_cart_summary(
        cart_items,
        city=profile_obj.city or "",
        birthday_bonus_selected=False,
        birthday_bonus_allowed=birthday_bonus_allowed,
        user=request.user,
    )
    birthday_preview = calculate_cart_summary(
        cart_items,
        city=profile_obj.city or "",
        birthday_bonus_selected=True,
        birthday_bonus_allowed=birthday_bonus_allowed,
        user=request.user,
    )
    return render(
        request,
        "checkout.html",
        {
            "cart_items": pricing["items"],
            "pricing": pricing,
            "birthday_bonus_allowed": birthday_bonus_allowed,
            "birthday_preview": birthday_preview,
        },
    )


@login_required
@require_POST
def place_order(request):
    cart = request.session.get("cart", {})
    if not cart:
        return redirect("home")

    profile_obj, _ = Profile.objects.get_or_create(user=request.user)
    if not profile_obj.phone or not profile_obj.city or not profile_obj.address:
        messages.error(request, "Заповніть телефон, місто та адресу в профілі перед оформленням замовлення.")
        return redirect("profile")

    birthday_bonus_requested = request.POST.get("birthday_bonus_ack") == "on"
    birthday_bonus_allowed = is_birthday_bonus_available(profile_obj.birth_date)
    if birthday_bonus_requested and not birthday_bonus_allowed:
        messages.error(request, "Бонус до дня народження недоступний. Перевірте дату народження в профілі.")
        return redirect("checkout")

    cart_items = get_cart_items(cart)
    if not cart_items:
        messages.error(request, "Один із товарів у кошику більше недоступний. Перевірте кошик ще раз.")
        return redirect("cart_detail")
    if any(not item["is_available"] for item in cart_items):
        messages.error(request, "У кошику є товари з недостатнім залишком. Перевірте кошик перед оформленням.")
        return redirect("cart_detail")

    pricing = calculate_cart_summary(
        cart_items,
        city=profile_obj.city or "",
        birthday_bonus_selected=birthday_bonus_requested,
        birthday_bonus_allowed=birthday_bonus_allowed,
        user=request.user,
    )
    cart_items = pricing["items"]

    discount_parts = []
    if pricing["percent_discount"] > 0:
        discount_parts.append(pricing["percent_label"])
    if pricing["birthday_discount"] > 0:
        discount_parts.append("Бонус до дня народження")
    discount_label = ", ".join(discount_parts)

    try:
        with transaction.atomic():
            order = Order.objects.create(
                user=request.user,
                first_name=request.user.first_name,
                last_name=request.user.last_name,
                phone=profile_obj.phone,
                city=profile_obj.city,
                address=profile_obj.address,
                subtotal_price=pricing["subtotal"],
                discount_amount=pricing["total_discount"],
                discount_label=discount_label,
                birthday_verification_required=pricing["birthday_verification_required"],
                total_price=pricing["final_total"],
            )

            for item in cart_items:
                tracked_stock = get_tracked_stock(item["product"], item["variant"])
                if tracked_stock is not None and item["quantity"] > tracked_stock:
                    raise ValueError("insufficient stock")

                OrderItem.objects.create(
                    order=order,
                    product=item["product"],
                    product_name=item["product"].name,
                    variant_name=item["variant_name"] or DEFAULT_VARIANT_NAME,
                    extra=item.get("extra") or "",
                    glycerin_price=item.get("glycerin_price", 0),
                    price=item["unit_price"],
                    quantity=item["quantity"],
                )

                if item["variant"] and item["variant"].stock_qty is not None:
                    item["variant"].stock_qty = max(0, item["variant"].stock_qty - item["quantity"])
                    item["variant"].save(update_fields=["stock_qty"])
                elif item["product"].stock_qty is not None:
                    item["product"].stock_qty = max(0, item["product"].stock_qty - item["quantity"])
                    item["product"].save(update_fields=["stock_qty"])
    except (Product.DoesNotExist, ProductVariant.DoesNotExist, TypeError, ValueError):
        messages.error(request, "Один із товарів у кошику більше недоступний. Перевірте кошик ще раз.")
        return redirect("cart_detail")

    send_telegram_message(build_order_telegram_text(order))

    request.session["cart"] = {}
    return render(request, "order_success.html", {"order": order})


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.select_related("category", "subcategory", "brand_ref").prefetch_related("specifications"),
        slug=slug,
        is_active=True,
    )
    variants = product.variants.filter(is_active=True).order_by("id")
    primary_image_url = get_product_primary_image_url(product, variants_queryset=variants)
    compatible = list(product.compatible_products.filter(is_active=True).select_related("category", "subcategory", "brand_ref")[:4])
    similar_qs = product.similar_products.filter(is_active=True).exclude(pk=product.pk).select_related("category", "subcategory", "brand_ref")
    similar = list(similar_qs[:4])
    if not similar:
        related_products = Product.objects.filter(is_active=True).exclude(pk=product.pk).select_related("category", "subcategory", "brand_ref")
        if product.subcategory_id:
            similar = list(related_products.filter(subcategory=product.subcategory)[:4])
        if not similar:
            similar = list(related_products.filter(category=product.category)[:4])
    enrich_products_with_discount_data([product], user=request.user if request.user.is_authenticated else None)
    enrich_products_with_discount_data(compatible, user=request.user if request.user.is_authenticated else None)
    enrich_products_with_discount_data(similar, user=request.user if request.user.is_authenticated else None)
    _attach_card_image_urls(compatible)
    _attach_card_image_urls(similar)
    attach_product_taxonomy([product])
    attach_product_taxonomy(compatible)
    attach_product_taxonomy(similar)
    product_specs = build_product_specs(product)
    approved_reviews = product.reviews.filter(is_approved=True).select_related("user")
    review_stats = approved_reviews.aggregate(avg=Avg("rating"), count=Count("id"))
    product_brand = product.brand_ref

    category_url = reverse("catalog_page")
    if product.catalog_category:
        category_url = f"{category_url}?category={product.catalog_category.id}"

    subcategory_url = ""
    if product.catalog_category and product.catalog_subcategory:
        subcategory_url = f"{reverse('catalog_page')}?category={product.catalog_category.id}&subcategory={product.catalog_subcategory.id}"

    brand_url = ""
    if product_brand:
        brand_url = reverse("catalog_page")
        if product.catalog_category:
            brand_url = f"{brand_url}?category={product.catalog_category.id}&brand={product_brand.slug}"
        else:
            brand_url = f"{brand_url}?brand={product_brand.slug}"

    return render(
        request,
        "product_detail.html",
        {
            "product": product,
            "variants": variants,
            "primary_image_url": primary_image_url,
            "compatible": compatible,
            "similar": similar,
            "product_specs": product_specs,
            "reviews": approved_reviews,
            "review_average": review_stats["avg"] or 0,
            "review_count": review_stats["count"] or 0,
            "review_form": ReviewForm(prefix="product"),
            "category_url": category_url,
            "subcategory_url": subcategory_url,
            "brand_url": brand_url,
        },
    )


def product_detail_legacy(request, pk):
    product = get_object_or_404(Product.objects.only("slug"), pk=pk)
    return redirect("product_detail", slug=product.slug)

@login_required
def add_product_review(request, slug):
    if request.method != "POST":
        return redirect("product_detail", slug=slug)

    product = get_object_or_404(Product, slug=slug)
    form = ReviewForm(request.POST, prefix="product")
    if form.is_valid():
        Review.objects.update_or_create(
            user=request.user,
            product=product,
            defaults={"rating": form.cleaned_data["rating"], "text": form.cleaned_data["text"], "is_approved": False},
        )
        messages.success(request, "Ваш відгук збережено та передано на модерацію.")
    else:
        messages.error(request, "Не вдалося зберегти відгук. Перевірте заповнення форми.")
    return redirect("product_detail", slug=slug)


@login_required
def add_site_review(request):
    if request.method != "POST":
        return redirect("home")

    form = ReviewForm(request.POST, prefix="site")
    if form.is_valid():
        existing_review = Review.objects.filter(user=request.user, product__isnull=True).first()
        if existing_review:
            existing_review.rating = form.cleaned_data["rating"]
            existing_review.text = form.cleaned_data["text"]
            existing_review.is_approved = False
            existing_review.save(update_fields=["rating", "text", "is_approved"])
        else:
            Review.objects.create(
                user=request.user,
                product=None,
                rating=form.cleaned_data["rating"],
                text=form.cleaned_data["text"],
                is_approved=False,
            )
        messages.success(request, "Ваш відгук про сайт збережено та передано на модерацію.")
    else:
        messages.error(request, "Не вдалося зберегти відгук. Перевірте форму.")
    return redirect("home")


def password_reset_request_view(request):
    form = PasswordResetRequestForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()
        user = User.objects.filter(email__iexact=email).first()
        request.session["password_reset_email"] = email

        if user:
            recent_code_exists = PasswordResetCode.objects.filter(
                email__iexact=email,
                created_at__gte=timezone.now() - timedelta(seconds=60),
            ).exists()
            if not recent_code_exists:
                code = f"{random.randint(0, 999999):06d}"
                PasswordResetCode.objects.create(
                    user=user,
                    email=user.email,
                    code=code,
                    expires_at=timezone.now() + timedelta(minutes=10),
                )
                try:
                    send_reset_code(user.email, code)
                except Exception:
                    messages.error(request, "Не вдалося відправити код на email. Перевірте SMTP налаштування Gmail або спробуйте ще раз пізніше.")
                    return render(request, "account/password_reset_request.html", {"form": form})

        messages.success(request, "Якщо email існує в системі, код підтвердження вже відправлено або буде доступний за кілька секунд.")
        return redirect("password_reset_confirm")

    return render(request, "account/password_reset_request.html", {"form": form})


def password_reset_confirm_view(request):
    email = request.session.get("password_reset_email")
    if not email:
        messages.error(request, "Спочатку запросіть код для скидання пароля.")
        return redirect("password_reset_request")

    form = PasswordResetConfirmForm(request.POST or None)
    user = User.objects.filter(email__iexact=email).first()

    if request.method == "POST" and form.is_valid():
        password_code = None
        if user:
            password_code = PasswordResetCode.objects.filter(user=user, email__iexact=email, is_used=False).order_by("-created_at").first()

        if (not password_code) or password_code.expires_at < timezone.now() or password_code.code != form.cleaned_data["code"]:
            form.add_error("code", "Код не знайдено або більше не дійсний.")
        else:
            user.set_password(form.cleaned_data["new_password1"])
            user.save(update_fields=["password"])
            password_code.is_used = True
            password_code.save(update_fields=["is_used"])
            request.session.pop("password_reset_email", None)
            messages.success(request, "Пароль успішно змінено. Тепер можна увійти.")
            return redirect("account_login")

    return render(request, "account/password_reset_confirm.html", {"form": form, "email": email})
