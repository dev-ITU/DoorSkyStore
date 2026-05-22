from django.contrib import admin

from .models import CustomerEmailVerification, CustomerProfile, DeliveryAddress, EmailClientSettings


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


@admin.register(CustomerEmailVerification)
class CustomerEmailVerificationAdmin(admin.ModelAdmin):
    list_display = ('email', 'user', 'attempts', 'expires_at', 'verified_at', 'sent_at')
    search_fields = ('user__username', 'user__email', 'email')
    list_filter = ('verified_at', 'sent_at')
    readonly_fields = ('code_hash', 'created_at', 'sent_at', 'verified_at')


@admin.register(EmailClientSettings)
class EmailClientSettingsAdmin(admin.ModelAdmin):
    list_display = ('host', 'port', 'from_email', 'is_enabled', 'use_tls', 'use_ssl', 'updated_at')
    readonly_fields = ('encrypted_password', 'updated_at')
