from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe

from reports.documents import DOCUMENT_TYPES
from .models import Order, OrderItem, PaymentTransaction


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    autocomplete_fields = ('product',)
    readonly_fields = ('line_total_readonly',)

    @admin.display(description='Сумма')
    def line_total_readonly(self, obj):
        if obj.pk:
            return obj.line_total
        return '-'


class PaymentTransactionInline(admin.TabularInline):
    model = PaymentTransaction
    extra = 0
    can_delete = False
    readonly_fields = (
        'amount',
        'method',
        'status',
        'provider',
        'reference',
        'error_message',
        'created_at',
        'processed_at',
    )
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'customer_name',
        'customer_phone',
        'status',
        'payment_status',
        'payment_method',
        'stock_reserved',
        'subtotal',
        'created_at',
        'document_links',
    )
    list_filter = ('status', 'payment_status', 'payment_method', 'stock_reserved', 'created_at')
    search_fields = ('id', 'customer_name', 'customer_phone', 'customer_email', 'payment_reference')
    readonly_fields = ('subtotal', 'payment_reference', 'paid_at', 'created_at', 'updated_at', 'document_links')
    inlines = [OrderItemInline, PaymentTransactionInline]
    actions = ('reserve_orders', 'simulate_successful_payment', 'simulate_failed_payment', 'confirm_orders', 'cancel_orders')

    fieldsets = (
        ('Заказ', {
            'fields': ('status', 'stock_reserved', 'manager', 'subtotal', 'document_links'),
        }),
        ('Оплата', {
            'fields': ('payment_method', 'payment_status', 'payment_reference', 'paid_at', 'payment_comment'),
        }),
        ('Клиент', {
            'fields': (
                'user',
                'customer_type',
                'customer_name',
                'customer_phone',
                'customer_email',
                'company_name',
                'company_inn',
                'company_kpp',
                'company_address',
                'delivery_address',
            ),
        }),
        ('Комментарий', {
            'fields': ('comment',),
        }),
        ('Системное', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at'),
        }),
    )

    @admin.display(description='Документы')
    def document_links(self, obj):
        if not obj.pk:
            return '-'
        links = []
        for document_type, label in DOCUMENT_TYPES:
            pdf_url = reverse('order_document_pdf', kwargs={'pk': obj.pk, 'document_type': document_type})
            links.append(f'{label}: <a href="{pdf_url}">PDF</a>')
        links.append(f'<a href="{reverse("order_documents_zip", kwargs={"pk": obj.pk})}">PDF ZIP</a>')
        return mark_safe('<br>'.join(links))

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.recalculate()

    @admin.action(description='Зарезервировать склад')
    def reserve_orders(self, request, queryset):
        updated = 0
        for order in queryset:
            try:
                order.reserve_stock(created_by=request.user)
                updated += 1
            except ValidationError as exc:
                self.message_user(request, f'Заказ #{order.pk}: {exc}', messages.ERROR)
        self.message_user(request, f'Зарезервировано заказов: {updated}.', messages.SUCCESS)

    @admin.action(description='Имитировать успешную оплату')
    def simulate_successful_payment(self, request, queryset):
        updated = 0
        skipped = 0
        for order in queryset:
            if order.is_paid or order.status == Order.STATUS_CANCELLED:
                skipped += 1
                continue
            now = timezone.now()
            transaction = PaymentTransaction.objects.create(
                order=order,
                amount=order.subtotal,
                method=order.payment_method,
                status=PaymentTransaction.STATUS_SUCCEEDED,
                reference=PaymentTransaction.make_reference(order),
                payload={'source': 'admin_action', 'user_id': request.user.pk},
                processed_at=now,
            )
            order.mark_paid(
                reference=transaction.reference,
                paid_at=now,
                comment=f'Платеж проведен администратором {request.user.get_username()} через симулятор.',
            )
            updated += 1
        self.message_user(request, f'Оплачено через симулятор: {updated}. Пропущено: {skipped}.', messages.SUCCESS)

    @admin.action(description='Имитировать отказ оплаты')
    def simulate_failed_payment(self, request, queryset):
        updated = 0
        skipped = 0
        for order in queryset:
            if order.is_paid or order.status == Order.STATUS_CANCELLED:
                skipped += 1
                continue
            PaymentTransaction.objects.create(
                order=order,
                amount=order.subtotal,
                method=order.payment_method,
                status=PaymentTransaction.STATUS_FAILED,
                reference=PaymentTransaction.make_reference(order),
                error_message='Отказ оплаты через действие администратора.',
                payload={'source': 'admin_action', 'user_id': request.user.pk},
                processed_at=timezone.now(),
            )
            order.mark_payment_failed(f'Платеж отклонен администратором {request.user.get_username()} через симулятор.')
            updated += 1
        self.message_user(request, f'Отклонено через симулятор: {updated}. Пропущено: {skipped}.', messages.WARNING)

    @admin.action(description='Подтвердить и списать склад')
    def confirm_orders(self, request, queryset):
        updated = 0
        for order in queryset:
            try:
                order.confirm(manager=request.user)
                updated += 1
            except ValidationError as exc:
                self.message_user(request, f'Заказ #{order.pk}: {exc}', messages.ERROR)
        self.message_user(request, f'Подтверждено заказов: {updated}.', messages.SUCCESS)

    @admin.action(description='Отменить и снять резерв')
    def cancel_orders(self, request, queryset):
        updated = 0
        for order in queryset:
            try:
                order.cancel(user=request.user)
                updated += 1
            except ValidationError as exc:
                self.message_user(request, f'Заказ #{order.pk}: {exc}', messages.ERROR)
        self.message_user(request, f'Отменено заказов: {updated}.', messages.SUCCESS)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product', 'quantity', 'unit_price', 'line_total')
    search_fields = ('order__id', 'product__name', 'product__sku')
    autocomplete_fields = ('order', 'product')


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('reference', 'order', 'status', 'method', 'amount', 'created_at', 'processed_at')
    list_filter = ('status', 'method', 'created_at')
    search_fields = ('reference', 'order__id', 'order__customer_name', 'error_message')
    readonly_fields = ('created_at', 'processed_at')
    autocomplete_fields = ('order',)
