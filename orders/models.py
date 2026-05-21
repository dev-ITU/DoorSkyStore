import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone

from catalog.models import DoorProduct, StockItem, StockMovement


class Order(models.Model):
    STATUS_NEW = 'new'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_NEW, 'Новый'),
        (STATUS_CONFIRMED, 'Подтвержден'),
        (STATUS_IN_PROGRESS, 'В работе'),
        (STATUS_COMPLETED, 'Завершен'),
        (STATUS_CANCELLED, 'Отменен'),
    ]

    CUSTOMER_INDIVIDUAL = 'individual'
    CUSTOMER_COMPANY = 'company'

    CUSTOMER_TYPE_CHOICES = [
        (CUSTOMER_INDIVIDUAL, 'Физическое лицо'),
        (CUSTOMER_COMPANY, 'Юридическое лицо'),
    ]

    PAYMENT_CARD = 'card'
    PAYMENT_SBP = 'sbp'
    PAYMENT_BANK_TRANSFER = 'bank_transfer'
    PAYMENT_CASH_ON_DELIVERY = 'cash_on_delivery'

    PAYMENT_METHOD_CHOICES = [
        (PAYMENT_CARD, 'Банковская карта'),
        (PAYMENT_SBP, 'СБП'),
        (PAYMENT_BANK_TRANSFER, 'Безналичный перевод'),
        (PAYMENT_CASH_ON_DELIVERY, 'Оплата при получении'),
    ]

    PAYMENT_WAITING = 'waiting'
    PAYMENT_PROCESSING = 'processing'
    PAYMENT_PAID = 'paid'
    PAYMENT_FAILED = 'failed'
    PAYMENT_REFUNDED = 'refunded'

    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_WAITING, 'Ожидает оплаты'),
        (PAYMENT_PROCESSING, 'В обработке'),
        (PAYMENT_PAID, 'Оплачен'),
        (PAYMENT_FAILED, 'Ошибка оплаты'),
        (PAYMENT_REFUNDED, 'Возврат'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Пользователь',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='orders',
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Менеджер',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='managed_orders',
    )
    status = models.CharField('Статус', max_length=24, choices=STATUS_CHOICES, default=STATUS_NEW)
    public_key = models.UUIDField('Публичный ключ', default=uuid.uuid4, editable=False, unique=True)
    stock_reserved = models.BooleanField('Склад зарезервирован', default=False)
    customer_name = models.CharField('Имя клиента', max_length=160)
    customer_phone = models.CharField('Телефон', max_length=32)
    customer_email = models.EmailField('Email', blank=True)
    customer_type = models.CharField(
        'Тип покупателя',
        max_length=24,
        choices=CUSTOMER_TYPE_CHOICES,
        default=CUSTOMER_INDIVIDUAL,
    )
    company_name = models.CharField('Компания', max_length=220, blank=True)
    company_inn = models.CharField('ИНН', max_length=12, blank=True)
    company_kpp = models.CharField('КПП', max_length=9, blank=True)
    company_address = models.TextField('Юридический адрес', blank=True)
    delivery_address = models.TextField('Адрес доставки', blank=True)
    comment = models.TextField('Комментарий', blank=True)
    subtotal = models.DecimalField('Сумма', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    payment_method = models.CharField(
        'Способ оплаты',
        max_length=32,
        choices=PAYMENT_METHOD_CHOICES,
        default=PAYMENT_CARD,
    )
    payment_status = models.CharField(
        'Статус оплаты',
        max_length=24,
        choices=PAYMENT_STATUS_CHOICES,
        default=PAYMENT_WAITING,
    )
    payment_reference = models.CharField('Номер платежа', max_length=64, blank=True)
    payment_comment = models.TextField('Комментарий к оплате', blank=True)
    paid_at = models.DateTimeField('Дата оплаты', null=True, blank=True)
    created_at = models.DateTimeField('Создан', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлен', auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'
        permissions = [
            ('can_confirm_order', 'Может подтверждать заказы и списывать склад'),
            ('can_export_order_docs', 'Может выгружать документы по заказам'),
            ('can_simulate_payment', 'Может проводить имитацию оплаты'),
        ]

    def __str__(self):
        return f'Заказ #{self.pk or "new"} - {self.customer_name}'

    def get_absolute_url(self):
        return reverse('order_detail', kwargs={'pk': self.pk, 'public_key': self.public_key})

    def get_payment_url(self):
        return reverse('payment_simulation', kwargs={'pk': self.pk, 'public_key': self.public_key})

    @property
    def is_paid(self):
        return self.payment_status == self.PAYMENT_PAID

    @property
    def can_pay(self):
        return self.status != self.STATUS_CANCELLED and self.payment_status in {
            self.PAYMENT_WAITING,
            self.PAYMENT_PROCESSING,
            self.PAYMENT_FAILED,
        }

    def recalculate(self, save=True):
        total = sum((item.line_total for item in self.items.all()), Decimal('0.00'))
        self.subtotal = total
        if save:
            self.save(update_fields=['subtotal', 'updated_at'])
        return total

    @transaction.atomic
    def reserve_stock(self, created_by=None):
        if self.stock_reserved:
            return
        items = list(self.items.select_related('product'))
        if not items:
            raise ValidationError('В заказе нет товаров.')

        for item in items:
            stock = StockItem.objects.select_for_update().get(product=item.product)
            stock.reserve(item.quantity)
            StockMovement.objects.create(
                product=item.product,
                movement_type=StockMovement.TYPE_RESERVE,
                quantity=item.quantity,
                reference=f'order:{self.pk}',
                created_by=created_by,
            )
        self.stock_reserved = True
        self.save(update_fields=['stock_reserved', 'updated_at'])

    @transaction.atomic
    def release_stock(self, created_by=None):
        if not self.stock_reserved:
            return
        for item in self.items.select_related('product'):
            stock = StockItem.objects.select_for_update().get(product=item.product)
            stock.release(item.quantity)
            StockMovement.objects.create(
                product=item.product,
                movement_type=StockMovement.TYPE_RELEASE,
                quantity=item.quantity,
                reference=f'order:{self.pk}',
                created_by=created_by,
            )
        self.stock_reserved = False
        self.save(update_fields=['stock_reserved', 'updated_at'])

    @transaction.atomic
    def confirm(self, manager=None):
        if self.status == self.STATUS_CANCELLED:
            raise ValidationError('Нельзя подтвердить отмененный заказ.')
        self.reserve_stock(created_by=manager)
        for item in self.items.select_related('product'):
            stock = StockItem.objects.select_for_update().get(product=item.product)
            stock.commit_reserved(item.quantity)
            StockMovement.objects.create(
                product=item.product,
                movement_type=StockMovement.TYPE_SALE,
                quantity=-item.quantity,
                reference=f'order:{self.pk}',
                created_by=manager,
            )
        self.status = self.STATUS_CONFIRMED
        self.stock_reserved = False
        if manager:
            self.manager = manager
        self.save(update_fields=['status', 'stock_reserved', 'manager', 'updated_at'])

    def mark_payment_processing(self, comment=''):
        self.payment_status = self.PAYMENT_PROCESSING
        if comment:
            self.payment_comment = comment
        self.save(update_fields=['payment_status', 'payment_comment', 'updated_at'])

    def mark_paid(self, reference='', paid_at=None, comment=''):
        self.payment_status = self.PAYMENT_PAID
        self.payment_reference = reference or self.payment_reference
        self.paid_at = paid_at or timezone.now()
        if self.status == self.STATUS_NEW:
            self.status = self.STATUS_IN_PROGRESS
        if comment:
            self.payment_comment = comment
        self.save(update_fields=['payment_status', 'payment_reference', 'paid_at', 'status', 'payment_comment', 'updated_at'])

    def mark_payment_failed(self, comment=''):
        self.payment_status = self.PAYMENT_FAILED
        if comment:
            self.payment_comment = comment
        self.save(update_fields=['payment_status', 'payment_comment', 'updated_at'])

    def mark_refunded(self, comment=''):
        self.payment_status = self.PAYMENT_REFUNDED
        if comment:
            self.payment_comment = comment
        self.save(update_fields=['payment_status', 'payment_comment', 'updated_at'])

    @transaction.atomic
    def cancel(self, user=None):
        self.release_stock(created_by=user)
        self.status = self.STATUS_CANCELLED
        update_fields = ['status', 'updated_at']
        if self.is_paid:
            self.payment_status = self.PAYMENT_REFUNDED
            self.payment_comment = 'Оплата переведена в имитационный возврат при отмене заказа.'
            update_fields.extend(['payment_status', 'payment_comment'])
        self.save(update_fields=update_fields)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, verbose_name='Заказ', on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(DoorProduct, verbose_name='Товар', on_delete=models.PROTECT, related_name='order_items')
    quantity = models.PositiveIntegerField('Количество')
    unit_price = models.DecimalField('Цена за единицу', max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = 'Позиция заказа'
        verbose_name_plural = 'Позиции заказа'
        constraints = [
            models.UniqueConstraint(fields=['order', 'product'], name='unique_product_per_order'),
        ]

    def __str__(self):
        return f'{self.product.name} x {self.quantity}'

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError({'quantity': 'Количество должно быть больше нуля.'})
        if self.unit_price < 0:
            raise ValidationError({'unit_price': 'Цена не может быть отрицательной.'})


class PaymentTransaction(models.Model):
    STATUS_CREATED = 'created'
    STATUS_SUCCEEDED = 'succeeded'
    STATUS_FAILED = 'failed'
    STATUS_REFUNDED = 'refunded'

    STATUS_CHOICES = [
        (STATUS_CREATED, 'Создан'),
        (STATUS_SUCCEEDED, 'Успешен'),
        (STATUS_FAILED, 'Отклонен'),
        (STATUS_REFUNDED, 'Возврат'),
    ]

    order = models.ForeignKey(
        Order,
        verbose_name='Заказ',
        on_delete=models.CASCADE,
        related_name='payment_transactions',
    )
    amount = models.DecimalField('Сумма', max_digits=12, decimal_places=2)
    method = models.CharField('Способ оплаты', max_length=32, choices=Order.PAYMENT_METHOD_CHOICES)
    status = models.CharField('Статус', max_length=24, choices=STATUS_CHOICES, default=STATUS_CREATED)
    provider = models.CharField('Провайдер', max_length=80, default='DoorSky Pay Simulator')
    reference = models.CharField('Номер операции', max_length=64, unique=True)
    error_message = models.CharField('Ошибка', max_length=240, blank=True)
    payload = models.JSONField('Технические данные', default=dict, blank=True)
    created_at = models.DateTimeField('Создана', auto_now_add=True)
    processed_at = models.DateTimeField('Обработана', null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Платежная операция'
        verbose_name_plural = 'Платежные операции'

    def __str__(self):
        return f'{self.reference} - {self.order_id} - {self.get_status_display()}'

    @classmethod
    def make_reference(cls, order):
        return f'DSP-{timezone.now().strftime("%Y%m%d%H%M%S")}-{order.pk}-{uuid.uuid4().hex[:6].upper()}'
