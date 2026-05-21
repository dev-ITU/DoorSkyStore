from django.conf import settings
from django.db import models


class WebVisit(models.Model):
    DEVICE_DESKTOP = 'desktop'
    DEVICE_MOBILE = 'mobile'
    DEVICE_TABLET = 'tablet'
    DEVICE_BOT = 'bot'
    DEVICE_UNKNOWN = 'unknown'

    DEVICE_CHOICES = [
        (DEVICE_DESKTOP, 'Desktop'),
        (DEVICE_MOBILE, 'Mobile'),
        (DEVICE_TABLET, 'Tablet'),
        (DEVICE_BOT, 'Bot'),
        (DEVICE_UNKNOWN, 'Не определено'),
    ]

    CHANNEL_DIRECT = 'direct'
    CHANNEL_INTERNAL = 'internal'
    CHANNEL_SEARCH = 'organic_search'
    CHANNEL_SOCIAL = 'social'
    CHANNEL_PAID = 'paid'
    CHANNEL_EMAIL = 'email'
    CHANNEL_REFERRAL = 'referral'

    CHANNEL_CHOICES = [
        (CHANNEL_DIRECT, 'Прямой заход'),
        (CHANNEL_INTERNAL, 'Внутренний переход'),
        (CHANNEL_SEARCH, 'Поиск'),
        (CHANNEL_SOCIAL, 'Соцсети'),
        (CHANNEL_PAID, 'Реклама'),
        (CHANNEL_EMAIL, 'Email'),
        (CHANNEL_REFERRAL, 'Реферальный'),
    ]

    visitor_id = models.CharField('ID посетителя', max_length=40, db_index=True)
    session_key = models.CharField('Django session', max_length=80, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Пользователь',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='web_visits',
    )
    ip_address = models.GenericIPAddressField('IP', null=True, blank=True)
    user_agent = models.TextField('User-Agent', blank=True)
    device_type = models.CharField('Тип устройства', max_length=24, choices=DEVICE_CHOICES, default=DEVICE_UNKNOWN)
    device = models.CharField('Устройство', max_length=80, blank=True)
    browser = models.CharField('Браузер', max_length=80, blank=True)
    os = models.CharField('ОС', max_length=80, blank=True)
    country_code = models.CharField('Код страны', max_length=8, blank=True)
    country = models.CharField('Страна', max_length=120, blank=True)
    region = models.CharField('Регион', max_length=120, blank=True)
    city = models.CharField('Город', max_length=120, blank=True)
    referrer = models.URLField('Источник перехода', max_length=800, blank=True)
    referrer_domain = models.CharField('Домен источника', max_length=220, blank=True)
    traffic_channel = models.CharField(
        'Канал трафика',
        max_length=32,
        choices=CHANNEL_CHOICES,
        default=CHANNEL_DIRECT,
        db_index=True,
    )
    utm_source = models.CharField('UTM source', max_length=160, blank=True)
    utm_medium = models.CharField('UTM medium', max_length=160, blank=True)
    utm_campaign = models.CharField('UTM campaign', max_length=220, blank=True)
    utm_term = models.CharField('UTM term', max_length=220, blank=True)
    utm_content = models.CharField('UTM content', max_length=220, blank=True)
    landing_path = models.CharField('Страница входа', max_length=600, blank=True)
    exit_path = models.CharField('Последняя страница', max_length=600, blank=True)
    page_views_count = models.PositiveIntegerField('Просмотров за визит', default=0)
    started_at = models.DateTimeField('Начало визита', auto_now_add=True, db_index=True)
    last_seen_at = models.DateTimeField('Последняя активность', db_index=True)

    class Meta:
        ordering = ['-started_at']
        verbose_name = 'Визит'
        verbose_name_plural = 'Визиты'
        indexes = [
            models.Index(fields=['visitor_id', 'last_seen_at']),
            models.Index(fields=['country', 'city']),
            models.Index(fields=['device_type', 'browser']),
        ]

    def __str__(self):
        return f'{self.visitor_id} · {self.landing_path}'


class WebPageView(models.Model):
    visit = models.ForeignKey(WebVisit, verbose_name='Визит', on_delete=models.CASCADE, related_name='page_views')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Пользователь',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='web_page_views',
    )
    path = models.CharField('Путь', max_length=600, db_index=True)
    full_path = models.CharField('Полный путь', max_length=1000, blank=True)
    referrer = models.URLField('Источник перехода', max_length=800, blank=True)
    status_code = models.PositiveSmallIntegerField('HTTP статус', default=200)
    viewport_width = models.PositiveIntegerField('Ширина viewport', null=True, blank=True)
    viewport_height = models.PositiveIntegerField('Высота viewport', null=True, blank=True)
    screen_width = models.PositiveIntegerField('Ширина экрана', null=True, blank=True)
    screen_height = models.PositiveIntegerField('Высота экрана', null=True, blank=True)
    device_pixel_ratio = models.DecimalField('DPR', max_digits=4, decimal_places=2, null=True, blank=True)
    language = models.CharField('Язык браузера', max_length=40, blank=True)
    timezone = models.CharField('Часовой пояс браузера', max_length=80, blank=True)
    color_scheme = models.CharField('Цветовая схема', max_length=20, blank=True)
    connection_type = models.CharField('Тип сети', max_length=40, blank=True)
    engagement_seconds = models.PositiveIntegerField('Время на странице, сек.', default=0)
    created_at = models.DateTimeField('Просмотрена', auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Просмотр страницы'
        verbose_name_plural = 'Просмотры страниц'
        indexes = [
            models.Index(fields=['path', 'created_at']),
            models.Index(fields=['created_at', 'status_code']),
        ]

    def __str__(self):
        return self.path
