from django.contrib import admin, messages
from django.db import transaction

from .models import Category, DoorProduct, StockItem, StockMovement


class StockItemInline(admin.StackedInline):
    model = StockItem
    extra = 0
    can_delete = False
    fields = ('quantity', 'reserved_quantity', 'min_quantity', 'available_readonly', 'updated_at')
    readonly_fields = ('available_readonly', 'updated_at')

    @admin.display(description='Доступно')
    def available_readonly(self, obj):
        if obj.pk:
            return obj.available_quantity
        return 0


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(DoorProduct)
class DoorProductAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'sku',
        'category',
        'price',
        'opening_type',
        'available_quantity',
        'is_active',
    )
    list_filter = ('category', 'opening_type', 'material', 'color', 'is_active')
    search_fields = ('name', 'sku', 'description', 'material', 'color', 'finish')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [StockItemInline]
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Основное', {
            'fields': ('category', 'name', 'slug', 'sku', 'description', 'price', 'is_active'),
        }),
        ('Характеристики', {
            'fields': (
                'opening_type',
                'material',
                'color',
                'finish',
                ('width_min_mm', 'width_max_mm'),
                ('height_min_mm', 'height_max_mm'),
            ),
        }),
        ('Медиа и источник', {
            'fields': ('image', 'image_url', 'source_url'),
        }),
        ('Системное', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at'),
        }),
    )

    @admin.display(description='Доступно')
    def available_quantity(self, obj):
        return obj.available_quantity


@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ('product', 'quantity', 'reserved_quantity', 'available_quantity', 'min_quantity', 'needs_restock')
    list_filter = ('product__category',)
    search_fields = ('product__name', 'product__sku')
    actions = ('release_selected_reserves',)

    @admin.display(description='Доступно')
    def available_quantity(self, obj):
        return obj.available_quantity

    @admin.action(description='Снять весь резерв по выбранным позициям')
    def release_selected_reserves(self, request, queryset):
        with transaction.atomic():
            count = 0
            for stock in queryset.select_for_update():
                if stock.reserved_quantity:
                    StockMovement.objects.create(
                        product=stock.product,
                        movement_type=StockMovement.TYPE_RELEASE,
                        quantity=stock.reserved_quantity,
                        reference='admin',
                        created_by=request.user,
                    )
                    stock.reserved_quantity = 0
                    stock.save(update_fields=['reserved_quantity', 'updated_at'])
                    count += 1
        self.message_user(request, f'Резерв снят у позиций: {count}.', messages.SUCCESS)


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'product', 'movement_type', 'quantity', 'reference', 'created_by')
    list_filter = ('movement_type', 'created_at')
    search_fields = ('product__name', 'product__sku', 'reference', 'comment')
    readonly_fields = ('created_at',)

# Register your models here.
