from django.db import migrations, models


def _legacy_mojibake(value):
    return value.encode("utf-8").decode("cp1251")


OLD_TO_NEW_STATUS = {
    _legacy_mojibake("Нове"): "new",
    "Нове": "new",
    "new": "new",
    _legacy_mojibake("В обробці"): "processing",
    "В обробці": "processing",
    "processing": "processing",
    _legacy_mojibake("Відправлено"): "shipped",
    "Відправлено": "shipped",
    "shipped": "shipped",
    _legacy_mojibake("Доставлено"): "delivered",
    "Доставлено": "delivered",
    "delivered": "delivered",
}


def normalize_order_statuses(apps, schema_editor):
    Order = apps.get_model("app_web", "Order")
    for order in Order.objects.all().only("id", "status"):
        order.status = OLD_TO_NEW_STATUS.get(order.status, "new")
        order.save(update_fields=["status"])


class Migration(migrations.Migration):

    dependencies = [
        ("app_web", "0016_alter_orderitem_extra"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("new", "Нове"),
                    ("processing", "В обробці"),
                    ("shipped", "Відправлено"),
                    ("delivered", "Доставлено"),
                ],
                default="new",
                max_length=20,
                verbose_name="Статус",
            ),
        ),
        migrations.RunPython(normalize_order_statuses, migrations.RunPython.noop),
    ]
