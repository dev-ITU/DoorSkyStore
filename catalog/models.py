from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils.text import slugify


class Category(models.Model):
    name = models.CharField('Название', max_length=160, unique=True)
    slug = models.SlugField('URL-ярлык', max_length=180, unique=True)
    description = models.TextField('Описание', blank=True)
    source_url = models.URLField('Источник данных', blank=True)
    is_active = models.BooleanField('Активна', default=True)
    created_at = models.DateTimeField('Создана', auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'

    def __str__(self):
        return self.name


class ProductQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True, category__is_active=True)

    def storefront(self):
        return self.active().filter(Q(image__isnull=False, image__gt='') | Q(image_url__gt=''))

    def in_stock(self):
        return self.filter(stock__quantity__gt=models.F('stock__reserved_quantity'))


class DoorProduct(models.Model):
    OPENING_SLIDING = 'sliding'
    OPENING_SWING = 'swing'
    OPENING_HIDDEN = 'hidden'
    OPENING_PIVOT = 'pivot'
    OPENING_PARTITION = 'partition'

    OPENING_CHOICES = [
        (OPENING_SLIDING, 'Раздвижная'),
        (OPENING_SWING, 'Распашная'),
        (OPENING_HIDDEN, 'Скрытая'),
        (OPENING_PIVOT, 'Pivot'),
        (OPENING_PARTITION, 'Перегородка'),
    ]

    category = models.ForeignKey(
        Category,
        verbose_name='Категория',
        on_delete=models.PROTECT,
        related_name='products',
    )
    name = models.CharField('Название', max_length=220)
    slug = models.SlugField('URL-ярлык', max_length=240, unique=True, blank=True)
    sku = models.CharField('Артикул', max_length=64, unique=True)
    description = models.TextField('Описание', blank=True)
    price = models.DecimalField('Цена', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    width_min_mm = models.PositiveIntegerField('Мин. ширина, мм', default=700)
    width_max_mm = models.PositiveIntegerField('Макс. ширина, мм', default=1200)
    height_min_mm = models.PositiveIntegerField('Мин. высота, мм', default=2000)
    height_max_mm = models.PositiveIntegerField('Макс. высота, мм', default=3000)
    material = models.CharField('Материал', max_length=120, blank=True)
    color = models.CharField('Цвет профиля', max_length=120, blank=True)
    finish = models.CharField('Отделка', max_length=160, blank=True)
    opening_type = models.CharField('Тип открывания', max_length=24, choices=OPENING_CHOICES)
    image = models.ImageField('Изображение', upload_to='products/', blank=True)
    image_url = models.URLField('Внешнее изображение', blank=True)
    source_url = models.URLField('Источник', blank=True)
    is_active = models.BooleanField('Активен', default=True)
    created_at = models.DateTimeField('Создан', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлен', auto_now=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ['category__name', 'name']
        verbose_name = 'Дверь'
        verbose_name_plural = 'Двери'
        indexes = [
            models.Index(fields=['is_active', 'opening_type']),
            models.Index(fields=['price']),
        ]

    def __str__(self):
        return f'{self.name} ({self.sku})'

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or slugify(self.sku) or 'door'
            self.slug = base_slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('product_detail', kwargs={'slug': self.slug})

    @property
    def display_image(self):
        if self.image:
            return self.image.url
        return self.image_url

    @property
    def available_quantity(self):
        if hasattr(self, 'stock'):
            return self.stock.available_quantity
        return 0

    def clean(self):
        if self.width_min_mm > self.width_max_mm:
            raise ValidationError({'width_min_mm': 'Минимальная ширина не может быть больше максимальной.'})
        if self.height_min_mm > self.height_max_mm:
            raise ValidationError({'height_min_mm': 'Минимальная высота не может быть больше максимальной.'})


class StockItem(models.Model):
    product = models.OneToOneField(
        DoorProduct,
        verbose_name='Товар',
        on_delete=models.CASCADE,
        related_name='stock',
    )
    quantity = models.PositiveIntegerField('На складе', default=0)
    reserved_quantity = models.PositiveIntegerField('В резерве', default=0)
    min_quantity = models.PositiveIntegerField('Минимальный остаток', default=1)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Остаток'
        verbose_name_plural = 'Остатки'

    def __str__(self):
        return f'{self.product.sku}: {self.available_quantity} доступно'

    @property
    def available_quantity(self):
        return max(self.quantity - self.reserved_quantity, 0)

    @property
    def needs_restock(self):
        return self.available_quantity <= self.min_quantity

    def clean(self):
        if self.reserved_quantity > self.quantity:
            raise ValidationError({'reserved_quantity': 'Резерв не может быть больше фактического остатка.'})

    def reserve(self, quantity):
        if quantity <= 0:
            raise ValidationError('Количество для резерва должно быть больше нуля.')
        if self.available_quantity < quantity:
            raise ValidationError(
                f'Недостаточно товара "{self.product.name}". Доступно: {self.available_quantity}, запрошено: {quantity}.'
            )
        self.reserved_quantity += quantity
        self.full_clean()
        self.save(update_fields=['reserved_quantity', 'updated_at'])

    def release(self, quantity):
        if quantity <= 0:
            raise ValidationError('Количество для снятия резерва должно быть больше нуля.')
        if self.reserved_quantity < quantity:
            raise ValidationError('Нельзя снять больше резерва, чем есть.')
        self.reserved_quantity -= quantity
        self.save(update_fields=['reserved_quantity', 'updated_at'])

    def commit_reserved(self, quantity):
        if quantity <= 0:
            raise ValidationError('Количество списания должно быть больше нуля.')
        if self.reserved_quantity < quantity:
            raise ValidationError('Сначала зарезервируйте товар перед списанием.')
        if self.quantity < quantity:
            raise ValidationError('Фактический остаток меньше списываемого количества.')
        self.reserved_quantity -= quantity
        self.quantity -= quantity
        self.save(update_fields=['quantity', 'reserved_quantity', 'updated_at'])


class StockMovement(models.Model):
    TYPE_INCOME = 'income'
    TYPE_WRITE_OFF = 'write_off'
    TYPE_RESERVE = 'reserve'
    TYPE_RELEASE = 'release'
    TYPE_SALE = 'sale'
    TYPE_ADJUSTMENT = 'adjustment'

    MOVEMENT_TYPES = [
        (TYPE_INCOME, 'Поступление'),
        (TYPE_WRITE_OFF, 'Списание'),
        (TYPE_RESERVE, 'Резерв'),
        (TYPE_RELEASE, 'Снятие резерва'),
        (TYPE_SALE, 'Продажа'),
        (TYPE_ADJUSTMENT, 'Корректировка'),
    ]

    product = models.ForeignKey(
        DoorProduct,
        verbose_name='Товар',
        on_delete=models.PROTECT,
        related_name='stock_movements',
    )
    movement_type = models.CharField('Тип операции', max_length=24, choices=MOVEMENT_TYPES)
    quantity = models.IntegerField('Количество')
    reference = models.CharField('Основание', max_length=160, blank=True)
    comment = models.TextField('Комментарий', blank=True)
    created_by = models.ForeignKey(
        'auth.User',
        verbose_name='Автор',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField('Создано', auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Движение склада'
        verbose_name_plural = 'Движения склада'

    def __str__(self):
        return f'{self.get_movement_type_display()}: {self.product.sku} x {self.quantity}'
