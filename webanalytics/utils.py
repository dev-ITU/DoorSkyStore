import re
from ipaddress import ip_address
from urllib.parse import parse_qs, unquote, urlparse

from .models import WebVisit


VISITOR_COOKIE = 'doorsky_visitor_id'
VISIT_TIMEOUT_MINUTES = 30

SKIPPED_PREFIXES = (
    '/admin/',
    '/api/',
    '/office/',
    '/reports/',
    '/accounts/',
    '/static/',
    '/media/',
    '/_analytics/',
    '/favicon.ico',
)

BOT_MARKERS = (
    'bot',
    'crawler',
    'spider',
    'slurp',
    'yandex',
    'googlebot',
    'bingpreview',
    'facebookexternalhit',
    'telegrambot',
    'whatsapp',
)

SEARCH_DOMAINS = ('google.', 'yandex.', 'bing.', 'duckduckgo.', 'mail.ru', 'rambler.', 'yahoo.')
SOCIAL_DOMAINS = ('vk.', 'vk.com', 'instagram.', 'facebook.', 't.me', 'telegram.', 'youtube.', 'ok.ru', 'pinterest.')
PAID_MEDIUMS = {'cpc', 'ppc', 'paid', 'paid_search', 'display', 'target', 'retargeting', 'ads'}

COUNTRY_NAMES_RU = {
    'AM': 'Армения',
    'AZ': 'Азербайджан',
    'BY': 'Беларусь',
    'CN': 'Китай',
    'DE': 'Германия',
    'ES': 'Испания',
    'FI': 'Финляндия',
    'FR': 'Франция',
    'GB': 'Великобритания',
    'GE': 'Грузия',
    'IT': 'Италия',
    'KZ': 'Казахстан',
    'NL': 'Нидерланды',
    'PL': 'Польша',
    'RU': 'Россия',
    'TR': 'Турция',
    'UA': 'Украина',
    'US': 'США',
    'UZ': 'Узбекистан',
}


def should_track_path(path):
    return bool(path) and not any(path.startswith(prefix) for prefix in SKIPPED_PREFIXES)


def clean_text(value, max_length=220):
    if not value:
        return ''
    value = unquote(str(value)).strip()
    value = re.sub(r'\s+', ' ', value)
    return value[:max_length]


def get_client_ip(request):
    for header in ('HTTP_CF_CONNECTING_IP', 'HTTP_TRUE_CLIENT_IP', 'HTTP_X_REAL_IP', 'HTTP_X_FORWARDED_FOR'):
        value = request.META.get(header)
        if value:
            candidate = value.split(',')[0].strip()
            try:
                return str(ip_address(candidate))
            except ValueError:
                continue
    remote_addr = request.META.get('REMOTE_ADDR', '')
    try:
        return str(ip_address(remote_addr))
    except ValueError:
        return None


def parse_user_agent(user_agent):
    agent = (user_agent or '').lower()
    device_type = WebVisit.DEVICE_DESKTOP
    device = 'Desktop'

    if not agent:
        device_type = WebVisit.DEVICE_UNKNOWN
        device = 'Не определено'
    elif any(marker in agent for marker in BOT_MARKERS):
        device_type = WebVisit.DEVICE_BOT
        device = 'Bot'
    elif 'ipad' in agent or 'tablet' in agent or 'kindle' in agent or ('android' in agent and 'mobile' not in agent):
        device_type = WebVisit.DEVICE_TABLET
        device = 'Tablet'
    elif 'mobile' in agent or 'iphone' in agent or 'ipod' in agent:
        device_type = WebVisit.DEVICE_MOBILE
        device = 'Mobile'

    if 'iphone' in agent:
        device = 'iPhone'
    elif 'ipad' in agent:
        device = 'iPad'
    elif 'android' in agent:
        device = 'Android'
    elif 'macintosh' in agent or 'mac os' in agent:
        device = 'Mac'
    elif 'windows' in agent:
        device = 'Windows PC'
    elif 'linux' in agent and device == 'Desktop':
        device = 'Linux PC'

    browser = 'Не определено'
    if 'edg/' in agent:
        browser = 'Microsoft Edge'
    elif 'opr/' in agent or 'opera' in agent:
        browser = 'Opera'
    elif 'yabrowser' in agent:
        browser = 'Яндекс Браузер'
    elif 'samsungbrowser' in agent:
        browser = 'Samsung Internet'
    elif 'crios' in agent or ('chrome' in agent and 'chromium' not in agent):
        browser = 'Chrome'
    elif 'firefox' in agent or 'fxios' in agent:
        browser = 'Firefox'
    elif 'safari' in agent:
        browser = 'Safari'
    elif 'chromium' in agent:
        browser = 'Chromium'

    os_name = 'Не определено'
    if 'android' in agent:
        os_name = 'Android'
    elif 'iphone' in agent or 'ipad' in agent or 'cpu os' in agent:
        os_name = 'iOS'
    elif 'windows nt' in agent:
        os_name = 'Windows'
    elif 'mac os x' in agent or 'macintosh' in agent:
        os_name = 'macOS'
    elif 'linux' in agent:
        os_name = 'Linux'

    return {
        'device_type': device_type,
        'device': device,
        'browser': browser,
        'os': os_name,
    }


def get_geo(request):
    country_code = clean_text(
        request.META.get('HTTP_CF_IPCOUNTRY')
        or request.META.get('HTTP_CLOUDFRONT_VIEWER_COUNTRY')
        or request.META.get('HTTP_X_VERCEL_IP_COUNTRY')
        or request.META.get('HTTP_X_APPENGINE_COUNTRY')
        or request.META.get('HTTP_X_GEO_COUNTRY'),
        8,
    ).upper()
    country_name = clean_text(
        request.META.get('HTTP_X_GEO_COUNTRY_NAME')
        or request.META.get('HTTP_X_COUNTRY_NAME')
        or COUNTRY_NAMES_RU.get(country_code, country_code),
        120,
    )
    return {
        'country_code': country_code,
        'country': country_name,
        'region': clean_text(
            request.META.get('HTTP_X_VERCEL_IP_COUNTRY_REGION')
            or request.META.get('HTTP_X_APPENGINE_REGION')
            or request.META.get('HTTP_X_GEO_REGION'),
            120,
        ),
        'city': clean_text(
            request.META.get('HTTP_CF_IPCITY')
            or request.META.get('HTTP_X_VERCEL_IP_CITY')
            or request.META.get('HTTP_X_APPENGINE_CITY')
            or request.META.get('HTTP_X_GEO_CITY'),
            120,
        ),
    }


def parse_referrer(request):
    referrer = clean_text(request.META.get('HTTP_REFERER'), 800)
    domain = ''
    if referrer:
        domain = urlparse(referrer).netloc.lower().removeprefix('www.')
    host = request.get_host().split(':')[0].lower()
    if domain and domain == host:
        channel = WebVisit.CHANNEL_INTERNAL
    elif not domain:
        channel = WebVisit.CHANNEL_DIRECT
    elif any(search_domain in domain for search_domain in SEARCH_DOMAINS):
        channel = WebVisit.CHANNEL_SEARCH
    elif any(social_domain in domain for social_domain in SOCIAL_DOMAINS):
        channel = WebVisit.CHANNEL_SOCIAL
    else:
        channel = WebVisit.CHANNEL_REFERRAL
    return referrer, domain, channel


def get_utm(request):
    query = parse_qs(request.META.get('QUERY_STRING', ''), keep_blank_values=False)
    utm = {
        'utm_source': clean_text((query.get('utm_source') or [''])[0], 160),
        'utm_medium': clean_text((query.get('utm_medium') or [''])[0], 160),
        'utm_campaign': clean_text((query.get('utm_campaign') or [''])[0], 220),
        'utm_term': clean_text((query.get('utm_term') or [''])[0], 220),
        'utm_content': clean_text((query.get('utm_content') or [''])[0], 220),
    }
    return utm


def traffic_channel_from_utm(utm, fallback_channel):
    medium = utm.get('utm_medium', '').lower()
    source = utm.get('utm_source', '').lower()
    if medium in PAID_MEDIUMS:
        return WebVisit.CHANNEL_PAID
    if medium == 'email' or source in {'email', 'newsletter'}:
        return WebVisit.CHANNEL_EMAIL
    if source and any(social_domain.replace('.', '') in source for social_domain in SOCIAL_DOMAINS):
        return WebVisit.CHANNEL_SOCIAL
    return fallback_channel
