import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models
from django.utils import timezone


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
    email_verified_at = models.DateTimeField('Email подтвержден', null=True, blank=True)
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

    @property
    def is_email_verified(self):
        return bool(self.email_verified_at and self.user.email)


class CustomerEmailVerification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Пользователь',
        on_delete=models.CASCADE,
        related_name='email_verification_codes',
    )
    email = models.EmailField('Email')
    code_hash = models.CharField('Hash кода', max_length=128)
    attempts = models.PositiveSmallIntegerField('Попытки', default=0)
    max_attempts = models.PositiveSmallIntegerField('Максимум попыток', default=5)
    expires_at = models.DateTimeField('Действует до')
    verified_at = models.DateTimeField('Подтвержден', null=True, blank=True)
    created_at = models.DateTimeField('Создан', auto_now_add=True)
    sent_at = models.DateTimeField('Отправлен', auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Код подтверждения email'
        verbose_name_plural = 'Коды подтверждения email'
        indexes = [
            models.Index(fields=['user', 'email', 'verified_at']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return f'{self.email} для {self.user}'

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def can_attempt(self):
        return not self.verified_at and not self.is_expired and self.attempts < self.max_attempts


class EmailClientSettings(models.Model):
    is_enabled = models.BooleanField('Включить отправку через эти настройки', default=False)
    host = models.CharField('SMTP host', max_length=255, blank=True)
    port = models.PositiveIntegerField('SMTP port', default=587)
    username = models.CharField('SMTP логин', max_length=255, blank=True)
    encrypted_password = models.TextField('SMTP пароль', blank=True)
    from_email = models.CharField('Email отправителя', max_length=255, blank=True)
    use_tls = models.BooleanField('TLS', default=True)
    use_ssl = models.BooleanField('SSL', default=False)
    timeout_seconds = models.PositiveIntegerField('Таймаут, сек.', default=15)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Обновил',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Настройки почтового клиента'
        verbose_name_plural = 'Настройки почтового клиента'

    def __str__(self):
        return self.host or 'Настройки почтового клиента'

    def save(self, *args, **kwargs):
        if not self.pk:
            self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        settings_object, _ = cls.objects.get_or_create(pk=1)
        return settings_object

    @staticmethod
    def _fernet():
        digest = hashlib.sha256(settings.SECRET_KEY.encode('utf-8')).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    def set_password(self, raw_password):
        self.encrypted_password = self._fernet().encrypt(raw_password.encode('utf-8')).decode('ascii')

    def get_password(self):
        if not self.encrypted_password:
            return ''
        try:
            return self._fernet().decrypt(self.encrypted_password.encode('ascii')).decode('utf-8')
        except (InvalidToken, UnicodeDecodeError, ValueError):
            return ''

    @property
    def has_password(self):
        return bool(self.encrypted_password and self.get_password())

    @property
    def is_configured(self):
        if not self.is_enabled or not self.host or not self.from_email:
            return False
        if self.use_tls and self.use_ssl:
            return False
        if self.username and not self.has_password:
            return False
        return True


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
