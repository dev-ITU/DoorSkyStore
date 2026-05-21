from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, DoorProduct, StockItem


class SeoEndpointTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name='Раздвижные', slug='sliding')
        product = DoorProduct.objects.create(
            category=category,
            name='Slide SEO',
            slug='slide-seo',
            sku='DSK-SEO-1',
            price=120000,
            opening_type=DoorProduct.OPENING_SLIDING,
            is_active=True,
        )
        StockItem.objects.create(product=product, quantity=3, reserved_quantity=0)

    def test_sitemap_contains_catalog_and_active_products(self):
        response = self.client.get(reverse('sitemap'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/xml')
        self.assertContains(response, reverse('catalog'), html=False)
        self.assertContains(response, '/catalog/slide-seo/', html=False)

    def test_robots_txt_points_to_sitemap_and_blocks_private_sections(self):
        response = self.client.get(reverse('robots_txt'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain; charset=utf-8')
        self.assertContains(response, 'Disallow: /office/', html=False)
        self.assertContains(response, 'Disallow: /orders/', html=False)
        self.assertContains(response, 'Sitemap:', html=False)
