from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .cache import bump_catalog_cache_version
from .models import Category, DoorProduct, StockItem


@receiver([post_save, post_delete], sender=Category)
@receiver([post_save, post_delete], sender=DoorProduct)
@receiver([post_save, post_delete], sender=StockItem)
def invalidate_catalog_cache(**kwargs):
    bump_catalog_cache_version()
