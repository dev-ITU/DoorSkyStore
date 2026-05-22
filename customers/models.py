from django.conf import settings
from django.db import models


class CustomerProfile(models.Model):
    CUSTOMER_INDIVIDUAL = 'individual'
    CUSTOMER_COMPANY = 'company'

    CUSTOMER_TYPE_CHOICES = [
        (CUSTOMER_INDIVIDUAL, 'Физическое лицо'),
        (CUSTOMER_COMPANY, 'Юридическое лицо'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name='Пользователь',
        on_delete=models.CASCADE,
        related_name='customer_profile',
    )
    full_name = models.CharField('Имя покупателя', max_length=160, blank=True)
    phone = models.CharField('Телефон', max_length=32, blank=True)
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
    default_address = models.ForeignKey(
        'DeliveryAddress',
        verbose_name='Адрес по умолчанию',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
    updated_at = models.DateTimeField('Обновлен', auto_now=True)

    class Meta:
        verbose_name = 'Профиль покупателя'
        verbose_name_plural = 'Профили покупателей'

    def __str__(self):
        return self.full_name or self.user.get_username()


class DeliveryAddress(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Пользователь',
        on_delete=models.CASCADE,
        related_name='delivery_addresses',
    )
    title = models.CharField('Название', max_length=120, default='Основной адрес')
    recipient_name = models.CharField('Получатель', max_length=160, blank=True)
    phone = models.CharField('Телефон', max_length=32, blank=True)
    address = models.TextField('Адрес доставки')
    is_default = models.BooleanField('По умолчанию', default=False)
    created_at = models.DateTimeField('Создан', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлен', auto_now=True)

    class Meta:
        ordering = ['-is_default', '-updated_at']
        verbose_name = 'Адрес доставки'
        verbose_name_plural = 'Адреса доставки'

    def __str__(self):
        return self.title
