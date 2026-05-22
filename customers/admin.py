from django.contrib import admin

from .models import CustomerProfile, DeliveryAddress


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'full_name', 'phone', 'customer_type', 'updated_at')
    search_fields = ('user__username', 'user__email', 'full_name', 'phone', 'company_name', 'company_inn')
    list_filter = ('customer_type',)


@admin.register(DeliveryAddress)
class DeliveryAddressAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'recipient_name', 'phone', 'is_default', 'updated_at')
    search_fields = ('user__username', 'recipient_name', 'phone', 'address')
    list_filter = ('is_default',)
