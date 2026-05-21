from decimal import Decimal, InvalidOperation

from django.core.cache import cache
from django.db.models import Q
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .cache import (
    catalog_cache_key,
    catalog_cache_timeout,
    catalog_facets_payload,
    product_base_payload,
    product_payloads_for_cart,
    query_signature,
)
from .models import Category, DoorProduct


def _decimal_param(value):
    if value in (None, ''):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ('id', 'name', 'slug', 'description', 'source_url')


class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    available_quantity = serializers.IntegerField(read_only=True)
    cart_quantity = serializers.SerializerMethodField()
    remaining_quantity = serializers.SerializerMethodField()
    display_image = serializers.CharField(read_only=True)
    detail_url = serializers.CharField(source='get_absolute_url', read_only=True)
    opening_type_label = serializers.CharField(source='get_opening_type_display', read_only=True)

    class Meta:
        model = DoorProduct
        fields = (
            'id',
            'name',
            'slug',
            'sku',
            'category',
            'description',
            'price',
            'width_min_mm',
            'width_max_mm',
            'height_min_mm',
            'height_max_mm',
            'material',
            'color',
            'finish',
            'opening_type',
            'opening_type_label',
            'display_image',
            'source_url',
            'available_quantity',
            'cart_quantity',
            'remaining_quantity',
            'detail_url',
        )

    def _cart_quantity(self, product):
        request = self.context.get('request')
        if not request:
            return 0
        cart = request.session.get('doorsky_cart', {})
        try:
            return int(cart.get(str(product.pk), 0))
        except (TypeError, ValueError):
            return 0

    def get_cart_quantity(self, product):
        return self._cart_quantity(product)

    def get_remaining_quantity(self, product):
        return max(product.available_quantity - self._cart_quantity(product), 0)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    lookup_field = 'slug'


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductSerializer
    lookup_field = 'slug'

    def list(self, request, *args, **kwargs):
        cache_key = catalog_cache_key(
            'product-list',
            request.scheme,
            request.get_host(),
            query_signature(request.query_params),
        )
        base_payload = cache.get(cache_key)

        if base_payload is None:
            queryset = self.filter_queryset(self.get_queryset())
            page = self.paginate_queryset(queryset)
            if page is not None:
                base_payload = {
                    'count': self.paginator.page.paginator.count,
                    'next': self.paginator.get_next_link(),
                    'previous': self.paginator.get_previous_link(),
                    'results': [product_base_payload(product) for product in page],
                }
            else:
                base_payload = {
                    'results': [product_base_payload(product) for product in queryset],
                }
            cache.set(cache_key, base_payload, catalog_cache_timeout())

        cart = request.session.get('doorsky_cart', {})
        payload = dict(base_payload)
        payload['results'] = product_payloads_for_cart(base_payload['results'], cart)
        return Response(payload)

    def get_queryset(self):
        queryset = DoorProduct.objects.active().select_related('category', 'stock')
        params = self.request.query_params

        query = params.get('q')
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query)
                | Q(sku__icontains=query)
                | Q(description__icontains=query)
                | Q(material__icontains=query)
                | Q(color__icontains=query)
                | Q(finish__icontains=query)
            )

        category = params.get('category')
        if category:
            if category.isdigit():
                queryset = queryset.filter(category_id=category)
            else:
                queryset = queryset.filter(category__slug=category)

        for field in ('material', 'color', 'opening_type'):
            value = params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})

        min_price = _decimal_param(params.get('min_price'))
        if min_price is not None:
            queryset = queryset.filter(price__gte=min_price)

        max_price = _decimal_param(params.get('max_price'))
        if max_price is not None:
            queryset = queryset.filter(price__lte=max_price)

        if params.get('in_stock') in ('1', 'true', 'on'):
            queryset = queryset.in_stock()

        ordering = params.get('ordering')
        if ordering in ('price', '-price', 'name', '-name', 'created_at', '-created_at'):
            queryset = queryset.order_by(ordering)

        return queryset

    @action(detail=False, methods=['get'])
    def facets(self, request):
        payload = catalog_facets_payload()
        return Response(
            {
                'materials': payload['materials'],
                'colors': payload['colors'],
                'opening_types': payload['opening_types'],
            }
        )
