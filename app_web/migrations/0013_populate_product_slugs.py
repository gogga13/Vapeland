from django.db import migrations
from django.utils.text import slugify


def populate_product_slugs(apps, schema_editor):
    Product = apps.get_model("app_web", "Product")

    for product in Product.objects.order_by("id"):
        if product.slug:
            continue

        base = slugify(product.name) or slugify(product.sku) or f"product-{product.id}"
        slug = base
        counter = 2
        while Product.objects.exclude(pk=product.pk).filter(slug=slug).exists():
            slug = f"{base}-{counter}"
            counter += 1

        product.slug = slug
        product.save(update_fields=["slug"])


class Migration(migrations.Migration):

    dependencies = [
        ("app_web", "0012_product_slug"),
    ]

    operations = [
        migrations.RunPython(populate_product_slugs, migrations.RunPython.noop),
    ]
