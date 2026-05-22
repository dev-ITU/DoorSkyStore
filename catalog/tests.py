from django.core.cache import cache
from django.test import Client
from django.test import TestCase
from django.urls import reverse

from .models import Category, DoorProduct, StockItem


class ProductApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.category = Category.objects.create(name='Стеклянные двери', slug='glass')
        self.product = DoorProduct.objects.create(
            category=self.category,
            name='AG-SLIM',
            slug='ag-slim',
            sku='DSK-TEST-1',
            price=100000,
            material='Алюминий / стекло',
            color='Черный',
            finish='Прозрачное стекло',
            opening_type=DoorProduct.OPENING_SWING,
            image_url='https://example.com/ag-slim.jpg',
        )
        StockItem.objects.create(product=self.product, quantity=3, reserved_quantity=1)

    def test_product_api_filters_by_stock_and_category(self):
        response = self.client.get(
            reverse('product-list'),
            {'in_stock': '1', 'category': self.category.slug, 'q': 'AG'},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['count'], 1)
        self.assertEqual(payload['results'][0]['available_quantity'], 2)

    def test_product_api_excludes_out_of_stock_when_requested(self):
        self.product.stock.reserved_quantity = 3
        self.product.stock.save()

        response = self.client.get(reverse('product-list'), {'in_stock': '1'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 0)

    def test_product_api_ignores_invalid_price_filters(self):
        response = self.client.get(reverse('product-list'), {'min_price': 'bad', 'max_price': '-100'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)

    def test_product_api_cache_invalidates_when_stock_changes(self):
        response = self.client.get(reverse('product-list'), {'in_stock': '1'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'][0]['available_quantity'], 2)

        self.product.stock.quantity = 8
        self.product.stock.save()
        response = self.client.get(reverse('product-list'), {'in_stock': '1'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'][0]['available_quantity'], 7)

    def test_cached_product_api_keeps_cart_fields_per_session(self):
        session = self.client.session
        session['doorsky_cart'] = {str(self.product.pk): 1}
        session.save()

        response = self.client.get(reverse('product-list'))
        other_response = Client().get(reverse('product-list'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(other_response.status_code, 200)
        self.assertEqual(response.json()['results'][0]['cart_quantity'], 1)
        self.assertEqual(response.json()['results'][0]['remaining_quantity'], 1)
        self.assertEqual(other_response.json()['results'][0]['cart_quantity'], 0)
        self.assertEqual(other_response.json()['results'][0]['remaining_quantity'], 2)

# Create your tests here.
