from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.text import slugify


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    patronymic = models.CharField(max_length=100, verbose_name="По батькові", blank=True)
    phone = models.CharField(max_length=20, verbose_name="Номер телефону", blank=True)
    address = models.CharField(max_length=255, verbose_name="Адреса доставки", blank=True, null=True)
    city = models.CharField(max_length=100, verbose_name="Місто", blank=True, null=True)
    birth_date = models.DateField(verbose_name="Дата народження", blank=True, null=True)

    def __str__(self):
        return f"Профіль {self.user.username}"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, "profile"):
        instance.profile.save()


class Category(models.Model):
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="children",
        null=True,
        blank=True,
        verbose_name="Батьківська категорія",
    )
    name = models.CharField(max_length=100, verbose_name="Назва категорії")
    image = models.ImageField(
        upload_to="categories/",
        verbose_name="Фонове зображення",
        blank=True,
        null=True,
    )
    is_featured = models.BooleanField(default=False, verbose_name="Показувати на головній")

    def __str__(self):
        if self.parent_id and self.parent:
            return f"{self.parent.name} / {self.name}"
        return self.name

    class Meta:
        verbose_name = "Категорія"
        verbose_name_plural = "Категорії"
        ordering = ["name"]


class Brand(models.Model):
    BRAND_NAME_ALIASES = {
        "elf-bar": "Elf Bar",
        "elfbar": "Elf Bar",
        "in-bottle": "Puzzle in Bottle",
        "lost-vape": "Lost Vape",
        "lostvaspe": "Lost Vape",
        "lostvape": "Lost Vape",
        "oxva": "OXVA",
    }

    name = models.CharField(max_length=100, unique=True, verbose_name="Назва бренду")
    slug = models.SlugField(max_length=120, unique=True, blank=True, verbose_name="Slug")
    categories = models.ManyToManyField(
        Category,
        blank=True,
        related_name="brands",
        verbose_name="Категорії",
    )

    @classmethod
    def canonicalize_name(cls, value):
        normalized = " ".join(str(value or "").strip().split())
        if not normalized:
            return ""
        return cls.BRAND_NAME_ALIASES.get(slugify(normalized), normalized)

    @classmethod
    def build_unique_slug(cls, name, pk=None):
        base = slugify(name) or "brand"
        slug = base
        counter = 2
        while cls.objects.exclude(pk=pk).filter(slug=slug).exists():
            slug = f"{base}-{counter}"
            counter += 1
        return slug

    @classmethod
    def get_or_create_from_name(cls, value):
        name = cls.canonicalize_name(value)
        if not name:
            return None

        brand = cls.objects.filter(name__iexact=name).first()
        if brand:
            changed_fields = []
            if brand.name != name:
                brand.name = name
                changed_fields.append("name")
            if not brand.slug:
                brand.slug = cls.build_unique_slug(name, pk=brand.pk)
                changed_fields.append("slug")
            if changed_fields:
                brand.save(update_fields=changed_fields)
            return brand

        return cls.objects.create(name=name, slug=cls.build_unique_slug(name))

    def save(self, *args, **kwargs):
        self.name = self.canonicalize_name(self.name)
        if not self.slug or Brand.objects.exclude(pk=self.pk).filter(slug=self.slug).exists():
            self.slug = self.build_unique_slug(self.name, pk=self.pk)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Бренд"
        verbose_name_plural = "Бренди"
        ordering = ["name"]


class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, verbose_name="Категорія")
    subcategory = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        related_name="subcategory_products",
        blank=True,
        null=True,
        verbose_name="Підкатегорія",
    )
    name = models.CharField(max_length=200, verbose_name="Назва товару")
    slug = models.SlugField(max_length=230, unique=True, blank=True, null=True, verbose_name="Slug")
    brand = models.CharField(max_length=100, verbose_name="Бренд", default="Vaporesso")
    brand_ref = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        related_name="products",
        blank=True,
        null=True,
        verbose_name="Бренд",
    )
    sku = models.CharField(max_length=50, verbose_name="Артикул", blank=True)
    description = models.TextField(verbose_name="Опис", blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Ціна (грн)")
    includes_glycerin = models.BooleanField(default=False, verbose_name="У комплекті є гліцерин")
    glycerin_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Гліцерин (грн)")
    stock_qty = models.PositiveIntegerField(
        verbose_name="Залишок",
        blank=True,
        null=True,
        help_text="Залиште порожнім, якщо облік залишків для товару не ведеться.",
    )
    image = models.ImageField(upload_to="products/", verbose_name="Фото товару", blank=True, null=True)
    is_active = models.BooleanField(default=True, verbose_name="Активний")
    compatible_products = models.ManyToManyField(
        "self",
        blank=True,
        symmetrical=False,
        related_name="compatible_with",
        verbose_name="Супутні товари",
    )
    similar_products = models.ManyToManyField(
        "self",
        blank=True,
        symmetrical=False,
        related_name="similar_to",
        verbose_name="Схожі товари",
    )

    @property
    def in_stock(self):
        return self.stock_qty is None or self.stock_qty > 0

    @property
    def display_brand(self):
        if self.brand_ref_id and self.brand_ref:
            return self.brand_ref.name
        return (self.brand or "").strip()

    @property
    def effective_glycerin_price(self):
        if self.includes_glycerin and self.glycerin_price and self.glycerin_price > 0:
            return self.glycerin_price
        return 0

    @property
    def effective_price(self):
        return self.price + self.effective_glycerin_price

    @property
    def category_path(self):
        if self.subcategory_id and self.subcategory:
            return [self.category, self.subcategory]
        return [self.category] if self.category_id else []

    def clean(self):
        super().clean()

        if self.category_id and self.category and self.category.parent_id and not self.subcategory_id:
            self.subcategory = self.category
            self.category = self.category.parent

        if self.subcategory_id:
            if not self.subcategory.parent_id:
                raise ValidationError({"subcategory": "Оберіть саме підкатегорію з батьківською категорією."})
            if self.category_id and self.subcategory.parent_id != self.category.id:
                raise ValidationError({"subcategory": "Підкатегорія повинна належати вибраній категорії."})
            self.category = self.subcategory.parent

    def _sync_category_links(self):
        if self.category_id and self.category and self.category.parent_id and not self.subcategory_id:
            self.subcategory = self.category
            self.category = self.category.parent

        if self.subcategory_id and self.subcategory:
            if self.subcategory.parent_id:
                self.category = self.subcategory.parent
            else:
                self.subcategory = None

    def _sync_brand_links(self):
        if self.brand_ref_id and self.brand_ref:
            self.brand = self.brand_ref.name
            return

        brand_obj = Brand.get_or_create_from_name(self.brand)
        if brand_obj:
            self.brand_ref = brand_obj
            self.brand = brand_obj.name

    def build_slug(self):
        base = slugify(self.name) or slugify(self.sku) or "product"
        slug = base
        counter = 2
        while Product.objects.exclude(pk=self.pk).filter(slug=slug).exists():
            slug = f"{base}-{counter}"
            counter += 1
        return slug

    def save(self, *args, **kwargs):
        self._sync_category_links()
        self._sync_brand_links()
        if self.glycerin_price and self.glycerin_price > 0:
            self.includes_glycerin = True
        if not self.slug:
            self.slug = self.build_slug()
        super().save(*args, **kwargs)
        if self.brand_ref_id and self.category_id:
            self.brand_ref.categories.add(self.category)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товари"
        ordering = ["name"]


class ProductSpecification(models.Model):
    product = models.ForeignKey(
        Product,
        related_name="specifications",
        on_delete=models.CASCADE,
        verbose_name="Товар",
    )
    label = models.CharField(max_length=100, verbose_name="Назва характеристики")
    value = models.CharField(max_length=255, verbose_name="Значення")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    is_highlight = models.BooleanField(default=False, verbose_name="Виділити неоном")

    def __str__(self):
        return f"{self.product.name}: {self.label}"

    class Meta:
        verbose_name = "Характеристика товару"
        verbose_name_plural = "Характеристики товарів"
        ordering = ["sort_order", "id"]


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, related_name="variants", on_delete=models.CASCADE)
    name = models.CharField(max_length=50, verbose_name="Назва (колір/смак)")
    stock_qty = models.PositiveIntegerField(
        verbose_name="Залишок варіанту",
        blank=True,
        null=True,
        help_text="Залиште порожнім, якщо залишок контролюється на рівні товару.",
    )
    is_active = models.BooleanField(default=True, verbose_name="Активний")
    image = models.ImageField(upload_to="products/variants/", blank=True, null=True, verbose_name="Фото варіанту")

    @property
    def in_stock(self):
        return self.stock_qty is None or self.stock_qty > 0

    def __str__(self):
        return f"{self.product.name} - {self.name}"

    class Meta:
        verbose_name = "Варіант товару"
        verbose_name_plural = "Варіанти товарів"
        constraints = [
            models.UniqueConstraint(fields=["product", "name"], name="unique_variant_name_per_product"),
        ]


class ProductDiscount(models.Model):
    TYPE_PERCENT = "percent"
    TYPE_FIXED = "fixed"
    TYPE_CHOICES = [
        (TYPE_PERCENT, "Відсоток"),
        (TYPE_FIXED, "Фіксована сума"),
    ]

    product = models.ForeignKey(
        Product,
        related_name="product_discounts",
        on_delete=models.CASCADE,
        verbose_name="Товар",
    )
    discount_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        verbose_name="Тип знижки",
    )
    value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Значення",
    )
    start_date = models.DateTimeField(verbose_name="Початок дії")
    end_date = models.DateTimeField(verbose_name="Кінець дії")
    is_active = models.BooleanField(default=True, verbose_name="Активна")

    def __str__(self):
        return f"Знижка для {self.product.name}"

    def is_valid(self, at=None):
        if not self.is_active:
            return False

        at = at or timezone.localtime()
        start = self.start_date
        end = self.end_date

        if timezone.is_naive(at):
            at = timezone.make_aware(at, timezone.get_current_timezone())
        if timezone.is_naive(start):
            start = timezone.make_aware(start, timezone.get_current_timezone())
        if timezone.is_naive(end):
            end = timezone.make_aware(end, timezone.get_current_timezone())

        return start <= at <= end

    class Meta:
        verbose_name = "Знижка на товар"
        verbose_name_plural = "Знижки на товари"
        ordering = ["-start_date", "-id"]
        indexes = [
            models.Index(fields=["is_active", "start_date", "end_date"]),
        ]


class Order(models.Model):
    STATUS_NEW = "new"
    STATUS_PROCESSING = "processing"
    STATUS_SHIPPED = "shipped"
    STATUS_DELIVERED = "delivered"
    STATUS_CHOICES = [
        (STATUS_NEW, "Нове"),
        (STATUS_PROCESSING, "В обробці"),
        (STATUS_SHIPPED, "Відправлено"),
        (STATUS_DELIVERED, "Доставлено"),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    phone = models.CharField(max_length=20)
    city = models.CharField(max_length=100)
    address = models.CharField(max_length=255)
    comment = models.TextField(blank=True, default="")
    subtotal_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_label = models.CharField(max_length=255, blank=True)
    birthday_verification_required = models.BooleanField(default=False)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW, verbose_name="Статус")

    def __str__(self):
        return f"Замовлення №{self.id} від {self.first_name}"

    class Meta:
        verbose_name = "Замовлення"
        verbose_name_plural = "Замовлення"
        ordering = ["-created_at"]


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    product_name = models.CharField(max_length=200, verbose_name="Назва товару (snapshot)", default="")
    variant_name = models.CharField(max_length=100, verbose_name="Варіант", default="Стандарт")
    extra = models.CharField(max_length=100, verbose_name="Додатково", default="", blank=True)
    glycerin_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Гліцерин (грн)")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)

    @property
    def line_total(self):
        return self.price * self.quantity

    def __str__(self):
        return f"{self.product_name} / {self.variant_name} x {self.quantity}"

    class Meta:
        verbose_name = "Позиція замовлення"
        verbose_name_plural = "Позиції замовлення"


class PasswordResetCode(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_reset_codes")
    email = models.EmailField()
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    def __str__(self):
        return f"Код скидання для {self.email}"

    class Meta:
        verbose_name = "Код скидання пароля"
        verbose_name_plural = "Коди скидання пароля"
        indexes = [
            models.Index(fields=["email", "created_at"]),
            models.Index(fields=["email", "code", "is_used"]),
        ]


class Review(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reviews")
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="reviews",
        null=True,
        blank=True,
        verbose_name="Товар",
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name="Рейтинг",
    )
    text = models.TextField(verbose_name="Текст відгуку")
    created_at = models.DateTimeField(auto_now_add=True)
    is_approved = models.BooleanField(default=False, verbose_name="Схвалено")

    def __str__(self):
        scope = self.product.name if self.product else "Відгук про сайт"
        return f"{self.user.username}: {scope}"

    class Meta:
        verbose_name = "Відгук"
        verbose_name_plural = "Відгуки"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="unique_review_per_user_product"),
        ]
