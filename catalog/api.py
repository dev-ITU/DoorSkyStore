from decimal import Decimal, InvalidOperation

from django.db.models import Q
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

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
        queryset = DoorProduct.objects.active()
        return Response(
            {
                'materials': sorted(filter(None, queryset.values_list('material', flat=True).distinct())),
                'colors': sorted(filter(None, queryset.values_list('color', flat=True).distinct())),
                'opening_types': [
                    {'value': value, 'label': label}
                    for value, label in DoorProduct.OPENING_CHOICES
                    if queryset.filter(opening_type=value).exists()
                ],
            }
        )
