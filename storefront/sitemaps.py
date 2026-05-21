from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from catalog.models import DoorProduct


class StaticViewSitemap(Sitemap):
    changefreq = 'daily'
    priority = 1.0

    def items(self):
        return ['catalog']

    def location(self, item):
        return reverse(item)


class ProductSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.8

    def items(self):
        return DoorProduct.objects.active().only('slug', 'updated_at').order_by('slug')

    def lastmod(self, item):
        return item.updated_at
