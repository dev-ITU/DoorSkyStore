from django.core.management.base import BaseCommand

from backoffice.views import ensure_default_groups


class Command(BaseCommand):
    help = 'Создает базовые роли DoorSkyStore для кастомной панели.'

    def handle(self, *args, **options):
        ensure_default_groups()
        self.stdout.write(self.style.SUCCESS('Базовые роли DoorSkyStore готовы.'))
