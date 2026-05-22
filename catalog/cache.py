from hashlib import sha256
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.db import connection

from .models import Category, DoorProduct

CATALOG_CACHE_VERSION_KEY = 'doorsky:catalog:version'


def catalog_cache_timeout():
    return int(getattr(settings, 'CATALOG_CACHE_TIMEOUT', 180))


def catalog_cache_version():
    version = cache.get(CATALOG_CACHE_VERSION_KEY)
    if version is None:
        version = 1
        cache.set(CATALOG_CACHE_VERSION_KEY, version, timeout=None)
    return version


def bump_catalog_cache_version():
    try:
        cache.incr(CATALOG_CACHE_VERSION_KEY)
    except ValueError:
        cache.set(CATALOG_CACHE_VERSION_KEY, 2, timeout=None)


def catalog_cache_key(namespace, *parts):
    raw = '|'.join(
        [
            str(catalog_cache_version()),
            str(connection.settings_dict.get('ENGINE', '')),
            str(connection.settings_dict.get('HOST', '')),
            str(connection.settings_dict.get('NAME', '')),
            namespace,
            *[str(part) for part in parts],
        ]
    )
    digest = sha256(raw.encode('utf-8')).hexdigest()
    return f'doorsky:catalog:{namespace}:{digest}'


def query_signature(query_params):
    pairs = []
    for key in sorted(query_params.keys()):
        values = query_params.getlist(key) if hasattr(query_params, 'getlist') else [query_params[key]]
        for value in values:
            pairs.append((key, value))
    return urlencode(pairs)


def product_base_payload(product):
    return {
        'id': product.pk,
        'name': product.name,
        'slug': product.slug,
        'sku': product.sku,
        'category': {
            'id': product.category.pk,
            'name': product.category.name,
            'slug': product.category.slug,
            'description': product.category.description,
            'source_url': product.category.source_url,
        },
        'description': product.description,
        'price': str(product.price),
        'width_min_mm': product.width_min_mm,
        'width_max_mm': product.width_max_mm,
        'height_min_mm': product.height_min_mm,
        'height_max_mm': product.height_max_mm,
        'material': product.material,
        'color': product.color,
        'finish': product.finish,
        'opening_type': product.opening_type,
        'opening_type_label': product.get_opening_type_display(),
        'display_image': product.display_image,
        'source_url': product.source_url,
        'available_quantity': product.available_quantity,
        'detail_url': product.get_absolute_url(),
    }


def product_payload_for_cart(base_payload, cart):
    payload = dict(base_payload)
    available_quantity = int(payload.get('available_quantity') or 0)
    cart_quantity = _cart_quantity_for_product(cart, payload['id'])
    payload['cart_quantity'] = cart_quantity
    payload['remaining_quantity'] = max(available_quantity - cart_quantity, 0)
    return payload


def product_payloads_for_cart(base_payloads, cart):
    return [product_payload_for_cart(payload, cart) for payload in base_payloads]


def catalog_facets_payload():
    key = catalog_cache_key('facets')
    cached = cache.get(key)
    if cached is not None:
        return cached

    products = DoorProduct.objects.storefront()
    categories = list(
        Category.objects.filter(is_active=True)
        .order_by('name')
        .values('id', 'name', 'slug', 'description', 'source_url')
    )
    payload = {
        'categories': categories,
        'materials': sorted(filter(None, products.values_list('material', flat=True).distinct())),
        'colors': sorted(filter(None, products.values_list('color', flat=True).distinct())),
        'opening_types': [
            {'value': value, 'label': label}
            for value, label in DoorProduct.OPENING_CHOICES
            if products.filter(opening_type=value).exists()
        ],
        'count': products.count(),
    }
    cache.set(key, payload, catalog_cache_timeout())
    return payload


def _cart_quantity_for_product(cart, product_id):
    try:
        return int(cart.get(str(product_id), 0))
    except (TypeError, ValueError):
        return 0
