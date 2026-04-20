from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from import_export import fields, resources
from import_export.admin import ImportExportModelAdmin
from import_export.formats import base_formats
from import_export.formats.base_formats import CSV
from import_export.widgets import BooleanWidget, DecimalWidget, ForeignKeyWidget
import tablib

from .models import Category, Order, OrderItem, Product, ProductDiscount, ProductVariant, Review


VARIANT_SEPARATOR = "|"
CATEGORY_NAME_ALIASES = {
    "pod system": "POD-системи",
    "liquids": "Рідини",
    "disposables": "Електронні сигарети",
    "cartridge": "Картриджі та випаровувачі для POD-систем",
}


class CategoryByNameWidget(ForeignKeyWidget):
    def clean(self, value, row=None, **kwargs):
        category_name = str(value or "").strip()
        if not category_name:
            raise ValidationError("Column 'category' is required for every imported product.")

        category_name = CATEGORY_NAME_ALIASES.get(category_name.lower(), category_name)
        category, _ = Category.objects.get_or_create(name=category_name)
        return category

    def render(self, value, obj=None, **kwargs):
        return value.name if value else ""


class ProductResource(resources.ModelResource):
    @staticmethod
    def _string_value(raw_value):
        if raw_value is None:
            return ""
        return str(raw_value).strip()

    @classmethod
    def _is_separator_only(cls, raw_value):
        normalized = cls._string_value(raw_value).replace(";", VARIANT_SEPARATOR)
        return bool(normalized) and normalized.replace(VARIANT_SEPARATOR, "") == ""

    category = fields.Field(
        column_name="category",
        attribute="category",
        widget=CategoryByNameWidget(Category, "name"),
    )
    price = fields.Field(
        column_name="price",
        attribute="price",
        widget=DecimalWidget(),
    )
    glycerin_price = fields.Field(
        column_name="glycerin_price",
        attribute="glycerin_price",
        widget=DecimalWidget(),
    )
    stock_qty = fields.Field(
        column_name="stock_qty",
        attribute="stock_qty",
        widget=DecimalWidget(),
    )
    is_active = fields.Field(
        column_name="is_active",
        attribute="is_active",
        widget=BooleanWidget(),
    )
    variant_names = fields.Field(column_name="variant_names")
    variant_images = fields.Field(column_name="variant_images")

    class Meta:
        model = Product
        fields = (
            "id",
            "category",
            "name",
            "brand",
            "sku",
            "description",
            "price",
            "glycerin_price",
            "stock_qty",
            "image",
            "is_active",
            "variant_names",
            "variant_images",
        )
        export_order = (
            "id",
            "category",
            "name",
            "brand",
            "sku",
            "description",
            "price",
            "glycerin_price",
            "stock_qty",
            "image",
            "is_active",
            "variant_names",
            "variant_images",
        )
        skip_unchanged = True
        report_skipped = True
        clean_model_instances = True
        use_transactions = True

    @staticmethod
    def _split_variants(raw_value):
        if raw_value in (None, ""):
            return []

        normalized = str(raw_value).replace(";", VARIANT_SEPARATOR)
        parts = [part.strip() for part in normalized.split(VARIANT_SEPARATOR)]
        return [part for part in parts if part]

    def before_import_row(self, row, **kwargs):
        row_number = kwargs.get("row_number")
        row_prefix = f"У рядку {row_number}" if row_number else "У цьому рядку"

        for key in (
            "category",
            "name",
            "brand",
            "sku",
            "description",
            "image",
            "variant_names",
            "variant_images",
        ):
            value = row.get(key)
            if isinstance(value, str):
                row[key] = value.strip()

        raw_variant_names = row.get("variant_names")
        raw_variant_images = row.get("variant_images")

        if self._is_separator_only(raw_variant_names):
            raise ValidationError(f"{row_prefix} залишився тільки розділювач '|' у variant_names.")

        if self._is_separator_only(raw_variant_images):
            raise ValidationError(f"{row_prefix} залишився тільки розділювач '|' у variant_images.")

        variant_names = self._split_variants(raw_variant_names)
        variant_images = self._split_variants(raw_variant_images)

        row["variant_names"] = VARIANT_SEPARATOR.join(variant_names) if variant_names else ""
        row["variant_images"] = VARIANT_SEPARATOR.join(variant_images) if variant_images else ""

        row_has_data = any(
            str(row.get(key, "")).strip()
            for key in ("id", "category", "name", "brand", "sku", "description", "price", "glycerin_price", "stock_qty", "image")
        )
        if not row_has_data and not variant_names and not variant_images:
            return

        if not row.get("brand"):
            row["brand"] = Product._meta.get_field("brand").default

        if row.get("is_active") in (None, ""):
            row["is_active"] = "1"

        if row.get("stock_qty") == "":
            row["stock_qty"] = None

        missing = [
            field_name
            for field_name in ("category", "name", "price")
            if not str(row.get(field_name, "")).strip()
        ]
        if missing:
            raise ValidationError(f"Missing required column values: {', '.join(missing)}.")

        if variant_images and len(variant_images) != len(variant_names):
            raise ValidationError("variant_images must contain the same number of items as variant_names.")

    def get_instance(self, instance_loader, row):
        product_id = str(row.get("id") or "").strip()
        if product_id.isdigit():
            return Product.objects.filter(pk=product_id).first()

        sku = str(row.get("sku") or "").strip()
        if sku:
            return Product.objects.filter(sku=sku).first()

        name = str(row.get("name") or "").strip()
        category_name = str(row.get("category") or "").strip()
        if name and category_name:
            return Product.objects.filter(name=name, category__name=category_name).first()

        return None

    def before_save_instance(self, instance, row, **kwargs):
        image_value = self._string_value(row.get("image"))
        if image_value:
            return

        if not instance.pk:
            return

        existing = Product.objects.filter(pk=instance.pk).only("image").first()
        if existing and existing.image:
            instance.image = existing.image

    def after_save_instance(self, instance, row, **kwargs):
        if kwargs.get("dry_run"):
            return

        variant_names = self._split_variants(row.get("variant_names"))
        if not variant_names:
            return

        variant_images = self._split_variants(row.get("variant_images"))
        image_map = {}
        if variant_images:
            image_map = {
                variant_name: variant_images[index]
                for index, variant_name in enumerate(variant_names)
            }

        kept_names = set()
        for variant_name in variant_names:
            variant, _ = ProductVariant.objects.get_or_create(product=instance, name=variant_name)
            image_value = image_map.get(variant_name, "")
            if image_value:
                variant.image = image_value
            variant.is_active = True
            variant.save()
            kept_names.add(variant_name)

        instance.variants.exclude(name__in=kept_names).delete()

    def dehydrate_variant_names(self, obj):
        return VARIANT_SEPARATOR.join(obj.variants.order_by("id").values_list("name", flat=True))

    def dehydrate_variant_images(self, obj):
        image_names = []
        for variant in obj.variants.order_by("id"):
            image_names.append(variant.image.name if variant.image else "")
        return VARIANT_SEPARATOR.join(image_names)


class GoogleSheetsXLSX(base_formats.XLSX):
    @staticmethod
    def _normalize_header(header):
        normalized = str(header or "").strip()
        canonical = normalized.lower().replace("і", "i")
        if canonical == "id":
            return "id"
        return normalized

    @staticmethod
    def _string_value(raw_value):
        if raw_value is None:
            return ""
        return str(raw_value).strip()

    @classmethod
    def _is_separator_only(cls, raw_value):
        normalized = cls._string_value(raw_value).replace(";", VARIANT_SEPARATOR)
        return bool(normalized) and normalized.replace(VARIANT_SEPARATOR, "") == ""

    @classmethod
    def _row_is_effectively_empty(cls, headers, row_values):
        for index, value in enumerate(row_values):
            header = headers[index] if index < len(headers) else ""
            normalized_value = cls._string_value(value)
            if not normalized_value:
                continue
            if header in {"variant_names", "variant_images"} and cls._is_separator_only(normalized_value):
                continue
            return False
        return True

    def create_dataset(self, in_stream):
        from io import BytesIO
        import openpyxl

        xlsx_book = openpyxl.load_workbook(BytesIO(in_stream), read_only=False, data_only=True)

        dataset = tablib.Dataset()
        sheet = xlsx_book.active
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return dataset

        headers = [self._normalize_header(header) for header in rows[0]]
        dataset.headers = headers
        for row in rows[1:]:
            row_values = list(row)
            if self._row_is_effectively_empty(headers, row_values):
                continue
            dataset.append(row_values)
        return dataset


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = ("name", "stock_qty", "is_active", "image")


class ProductDiscountInline(admin.TabularInline):
    model = ProductDiscount
    extra = 0
    fields = ("discount_type", "value", "start_date", "end_date", "is_active")


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    fields = ("product_name", "variant_name", "extra", "glycerin_price", "price", "quantity", "line_total_display")
    readonly_fields = ("product_name", "variant_name", "extra", "glycerin_price", "price", "quantity", "line_total_display")

    @admin.display(description="Сума позиції")
    def line_total_display(self, obj):
        return f"{obj.line_total:.2f} грн"


@admin.register(Product)
class ProductAdmin(ImportExportModelAdmin):
    resource_class = ProductResource
    formats = [CSV, GoogleSheetsXLSX]
    import_error_display = ("message", "row", "traceback")
    list_display = ("name", "brand", "sku", "slug", "price", "glycerin_price", "stock_qty", "category", "is_active")
    list_editable = ("price", "glycerin_price", "stock_qty", "is_active")
    list_filter = ("category", "brand", "is_active")
    search_fields = ("name", "brand", "sku", "slug", "description")
    autocomplete_fields = ("category",)
    filter_horizontal = ("compatible_products", "similar_products")
    inlines = [ProductVariantInline, ProductDiscountInline]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "is_featured")
    list_filter = ("is_featured",)
    search_fields = ("name",)
    autocomplete_fields = ("parent",)


@admin.register(ProductDiscount)
class ProductDiscountAdmin(admin.ModelAdmin):
    list_display = ("product", "discount_type", "value", "start_date", "end_date", "is_active", "currently_valid")
    list_filter = ("is_active", "discount_type", "start_date", "end_date")
    search_fields = ("product__name", "product__sku", "product__brand")
    autocomplete_fields = ("product",)
    date_hierarchy = "start_date"

    @admin.display(description="Діє зараз", boolean=True)
    def currently_valid(self, obj):
        return obj.is_valid()


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_link",
        "first_name",
        "last_name",
        "phone",
        "city",
        "total_price",
        "status",
        "birthday_verification_required",
        "created_at",
        "details_link",
    )
    list_editable = ("status",)
    list_filter = ("status", "birthday_verification_required", "created_at")
    search_fields = ("id", "first_name", "last_name", "phone", "city", "address", "comment")
    readonly_fields = (
        "user",
        "first_name",
        "last_name",
        "phone",
        "city",
        "address",
        "customer_email",
        "subtotal_price",
        "discount_amount",
        "discount_label",
        "birthday_verification_required",
        "total_price",
        "created_at",
    )
    inlines = [OrderItemInline]
    list_display_links = ()

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:order_id>/details/",
                self.admin_site.admin_view(self.order_details_view),
                name="app_web_order_details",
            ),
        ]
        return custom_urls + urls

    @admin.display(description="Замовлення")
    def order_link(self, obj):
        url = reverse("admin:app_web_order_details", args=[obj.pk])
        return format_html('<a href="{}"><strong>#{}</strong></a>', url, obj.pk)

    @admin.display(description="Email")
    def customer_email(self, obj):
        return obj.user.email if obj.user_id and obj.user and obj.user.email else "—"

    @admin.display(description="Подробнее")
    def details_link(self, obj):
        url = reverse("admin:app_web_order_details", args=[obj.pk])
        return format_html('<a class="button" href="{}">Подробнее</a>', url)

    def order_details_view(self, request, order_id):
        order = get_object_or_404(
            Order.objects.select_related("user").prefetch_related("items"),
            pk=order_id,
        )

        if request.method == "POST":
            new_status = request.POST.get("status", "").strip()
            comment = request.POST.get("comment", "").strip()
            valid_statuses = {value for value, _ in Order.STATUS_CHOICES}

            if new_status not in valid_statuses:
                messages.error(request, "Некоректний статус замовлення.")
                return redirect(request.path)

            changed_fields = []
            if order.status != new_status:
                order.status = new_status
                changed_fields.append("status")
            if order.comment != comment:
                order.comment = comment
                changed_fields.append("comment")

            if changed_fields:
                order.save(update_fields=changed_fields)
                self.message_user(request, "Замовлення оновлено.", level=messages.SUCCESS)
            else:
                self.message_user(request, "Змін немає.", level=messages.INFO)

            return redirect(request.path)

        item_rows = []
        for item in order.items.all():
            item_rows.append(
                {
                    "product_id": item.product_id,
                    "name": item.product_name,
                    "variant_name": item.variant_name,
                    "extra": item.extra,
                    "price": item.price,
                    "quantity": item.quantity,
                    "line_total": item.line_total,
                }
            )

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "original": order,
            "order": order,
            "status_choices": Order.STATUS_CHOICES,
            "item_rows": item_rows,
            "customer_name": f"{order.first_name} {order.last_name}".strip(),
            "customer_email_value": order.user.email if order.user_id and order.user and order.user.email else "Не вказано",
            "title": f"Замовлення #{order.id}",
        }
        return TemplateResponse(request, "admin/app_web/order/order_details.html", context)


@admin.action(description="Схвалити вибрані відгуки")
def approve_reviews(modeladmin, request, queryset):
    queryset.update(is_approved=True)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "rating", "is_approved", "created_at")
    list_filter = ("is_approved",)
    search_fields = ("user__username", "user__email", "product__name", "text")
    actions = [approve_reviews]
