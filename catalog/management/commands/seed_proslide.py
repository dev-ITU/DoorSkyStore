import html
import re
from decimal import Decimal
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand

from catalog.models import Category, DoorProduct, StockItem


BASE_URL = 'https://pro-slide.ru/'
USER_AGENT = 'DoorSkyStore source importer'

SOURCE_SECTIONS = [
    {
        'slug': 'razdvizhnye-peregorodki',
        'name': 'Раздвижные перегородки AG-SLIM',
        'path': '/razdvizhnye-peregorodki',
        'prefix': 'SLD',
        'opening': DoorProduct.OPENING_SLIDING,
        'material': 'Алюминий / стекло',
        'base_price': 148000,
        'description': (
            'Легкие раздвижные перегородки AG-SLIM из алюминиевого профиля и стекла для зонирования '
            'жилых и коммерческих помещений. Конструкция сохраняет свет, визуальную легкость и может '
            'использоваться как межкомнатное решение.'
        ),
    },
    {
        'slug': 'razdvizhnye-peregorodki-v-penal',
        'name': 'Раздвижные перегородки в пенал',
        'path': '/razdvizhnye-peregorodki#!/tab/820619248-4',
        'prefix': 'PNL',
        'opening': DoorProduct.OPENING_SLIDING,
        'material': 'Алюминий / стекло',
        'base_price': 162000,
        'description': (
            'Раздвижные перегородки, уходящие в пенал внутри стены. Такое решение освобождает проем, '
            'не занимает полезную площадь рядом с проходом и подходит для аккуратного скрытого монтажа.'
        ),
    },
    {
        'slug': 'sostavnye-stekla',
        'name': 'Раздвижные перегородки Composite',
        'path': '/razdvizhnaya-dver_composite',
        'prefix': 'CMP',
        'opening': DoorProduct.OPENING_SLIDING,
        'material': 'Алюминий / стекло',
        'base_price': 176000,
        'description': (
            'Composite - раздвижные перегородки с декоративным алюминиевым рисунком на стекле. '
            'Варианты INCLINE, LINE, HORIZON, STRIPE и другие дизайны используются как выразительный '
            'интерьерный акцент.'
        ),
    },
    {
        'slug': 'steklyannye-dveri',
        'name': 'Стеклянные двери',
        'path': '/raspashnye-dveri',
        'prefix': 'GLS',
        'opening': DoorProduct.OPENING_SWING,
        'material': 'Алюминий / стекло',
        'base_price': 89000,
        'description': (
            'Распашные стеклянные двери в тонком алюминиевом профиле. Подходят для межкомнатных '
            'проемов, кабинетов, гардеробных и зон, где важны светопрозрачность и строгая геометрия.'
        ),
    },
    {
        'slug': 'raspashnye-dveri-s-framugami',
        'name': 'Распашные двери с фрамугами',
        'path': '/raspashnye-dveri#!/tab/808135966-2',
        'prefix': 'FRM',
        'opening': DoorProduct.OPENING_SWING,
        'material': 'Алюминий / стекло',
        'base_price': 124000,
        'description': (
            'Распашные двери с фрамугами позволяют оформить высокий или широкий проем единой стеклянной '
            'композицией. Фрамуги визуально продолжают дверь и помогают сохранить пропорции интерьера.'
        ),
    },
    {
        'slug': 'hidden-paint',
        'name': 'Скрытые двери под покраску',
        'path': '/skrytye-dvernye-sistemy#!/tab/823204832-4',
        'prefix': 'HDN',
        'opening': DoorProduct.OPENING_HIDDEN,
        'material': 'Алюминий / МДФ',
        'base_price': 72000,
        'description': (
            'Скрытые дверные системы под покраску для интеграции полотна в стену. Дверь можно оформить '
            'в цвет стены, сделать почти незаметной или использовать как базу под индивидуальную отделку.'
        ),
    },
    {
        'slug': 'shpon',
        'name': 'Скрытые двери в натуральном шпоне',
        'path': '/skrytye-dvernye-sistemy',
        'prefix': 'VNR',
        'opening': DoorProduct.OPENING_HIDDEN,
        'material': 'Алюминий / шпон',
        'base_price': 116000,
        'description': (
            'Скрытые двери с отделкой натуральным шпоном. Решение объединяет скрытый короб, чистую '
            'плоскость стены и выразительную фактуру дерева.'
        ),
    },
    {
        'slug': 'keramogranit',
        'name': 'Скрытые двери с керамогранитом',
        'path': '/skrytye-dvernye-sistemy#!/tab/823204832-2',
        'prefix': 'CRM',
        'opening': DoorProduct.OPENING_HIDDEN,
        'material': 'Алюминий / керамогранит',
        'base_price': 146000,
        'description': (
            'Скрытые двери с керамогранитом для интерьеров, где дверное полотно должно поддерживать '
            'каменную, плиточную или крупноформатную отделку стены.'
        ),
    },
    {
        'slug': 'mirror',
        'name': 'Скрытые двери с зеркалом',
        'path': '/skrytye-dvernye-sistemy#!/tab/823204832-3',
        'prefix': 'MIR',
        'opening': DoorProduct.OPENING_HIDDEN,
        'material': 'Алюминий / зеркало',
        'base_price': 132000,
        'description': (
            'Скрытые двери с зеркальной поверхностью. Такой формат подходит для гардеробных, холлов и '
            'спален, где дверь одновременно работает как функциональная зеркальная плоскость.'
        ),
    },
    {
        'slug': 'pivot',
        'name': 'Поворотные двери PIVOT',
        'path': '/pivot',
        'prefix': 'PVT',
        'opening': DoorProduct.OPENING_PIVOT,
        'material': 'Алюминий / стекло',
        'base_price': 198000,
        'description': (
            'Поворотные двери PIVOT с центральной или смещенной осью открывания. Конструкция подходит '
            'для эффектных высоких полотен и акцентных проемов.'
        ),
    },
    {
        'slug': 'office-partitions',
        'name': 'Офисные перегородки',
        'path': '/razdvizhnye-peregorodki#!/tab/820619248-3',
        'prefix': 'OFF',
        'opening': DoorProduct.OPENING_PARTITION,
        'material': 'Алюминий / стекло',
        'base_price': 164000,
        'description': (
            'Офисные стеклянные перегородки для переговорных, кабинетов и рабочих зон. Система помогает '
            'разделять пространство, сохраняя визуальную прозрачность и контроль света.'
        ),
    },
    {
        'slug': 'wardrobe-partitions',
        'name': 'Гардеробные перегородки',
        'path': '/razdvizhnye-peregorodki#!/tab/820619248-2',
        'prefix': 'WRD',
        'opening': DoorProduct.OPENING_PARTITION,
        'material': 'Алюминий / стекло',
        'base_price': 142000,
        'description': (
            'Гардеробные перегородки в алюминиевом профиле для выделения зоны хранения. Стекло и '
            'декоративные раскладки помогают встроить гардеробную в общий стиль интерьера.'
        ),
    },
]

SOURCE_PREFIXES = {section['prefix'] for section in SOURCE_SECTIONS}
STOP_IMAGE_MARKERS = (
    'whatsapp',
    'telegram',
    'logo',
    'favicon',
    'black_matt',
    'dark_bronze',
    'champagne_matt',
    'gold_matt',
    'chrome_matt',
    'ral',
    'triplex',
)
STOP_IMAGE_URLS = {
    'https://static.tildacdn.com/tild6339-6537-4665-b365-393437353765/_2.png',
    'https://static.tildacdn.com/tild6539-3434-4161-a539-383236666239/_2.png',
}


class Command(BaseCommand):
    help = 'Импортирует категории и карточки из публичных страниц pro-slide.ru.'

    def add_arguments(self, parser):
        parser.add_argument('--max-per-section', type=int, default=15, help='Максимум карточек из одного раздела.')
        parser.add_argument('--no-network', action='store_true', help='Не запрашивать pro-slide.ru.')

    def handle(self, *args, **options):
        if options['no_network']:
            self.stdout.write(self.style.WARNING('Импорт пропущен: включен --no-network.'))
            return

        max_per_section = max(options['max_per_section'], 1)
        generated_skus = set()
        total = 0

        for section in SOURCE_SECTIONS:
            source_url = urljoin(BASE_URL, section['path'])
            category, _ = Category.objects.update_or_create(
                slug=section['slug'],
                defaults={
                    'name': section['name'],
                    'source_url': source_url,
                    'description': section['description'],
                    'is_active': True,
                },
            )

            items = self._source_items(source_url, section['name'])[:max_per_section]
            if not items:
                self.stdout.write(self.style.WARNING(f'{section["name"]}: карточки не найдены.'))
                continue

            for index, item in enumerate(items, start=1):
                sku = f'DSK-{section["prefix"]}-{index:03d}'
                price = Decimal(section['base_price'] + (index - 1) * 6500)
                product_name = self._product_name(section['name'], item['title'], index)
                stock_quantity = 4 + (index % 7)

                product, _ = DoorProduct.objects.update_or_create(
                    sku=sku,
                    defaults={
                        'category': category,
                        'name': product_name,
                        'slug': sku.lower(),
                        'description': (
                            self._description(section, item['title'], source_url)
                        ),
                        'price': price,
                        'width_min_mm': 700,
                        'width_max_mm': 1400,
                        'height_min_mm': 2000,
                        'height_max_mm': 3200,
                        'material': section['material'],
                        'color': '',
                        'finish': item['title'],
                        'opening_type': section['opening'],
                        'image_url': item['image_url'],
                        'source_url': source_url,
                        'is_active': True,
                    },
                )
                StockItem.objects.update_or_create(
                    product=product,
                    defaults={'quantity': stock_quantity, 'reserved_quantity': 0, 'min_quantity': 2},
                )
                generated_skus.add(sku)
                total += 1
                self.stdout.write(self.style.SUCCESS(f'{sku}: {product.name}'))

        self._deactivate_stale_products(generated_skus)
        self.stdout.write(self.style.SUCCESS(f'Импорт завершен. Активных source-карточек: {total}.'))

    def _source_items(self, source_url, section_name):
        response = requests.get(source_url, timeout=20, headers={'User-Agent': USER_AGENT})
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        named_items = self._extract_named_designs(soup)
        image_urls = self._extract_image_urls(response.text)
        image_items = [
            {'title': self._title_from_image_url(image_url, section_name, index), 'image_url': image_url}
            for index, image_url in enumerate(image_urls, start=1)
        ]
        return self._dedupe_items([*named_items, *image_items])

    def _extract_named_designs(self, soup):
        items = []
        for node in soup.select('.t537__itemwrapper'):
            image = node.select_one('[data-original]')
            caption = node.select_one('.t537__persdescr')
            image_url = image.get('data-original') if image else ''
            title = self._clean_text(caption.get_text(' ', strip=True)) if caption else ''
            if not image_url or not title:
                continue
            if self._is_usable_image(image_url):
                items.append({'title': title, 'image_url': image_url})
        return self._dedupe_items(items)

    def _extract_image_urls(self, text):
        decoded = html.unescape(text)
        urls = []
        urls.extend(
            re.findall(
                r'https://(?:static|thb)\.tildacdn\.com/[^\s"\'<>]+?\.(?:jpg|jpeg|png|webp|JPG|JPEG|PNG|WEBP)',
                decoded,
            )
        )
        urls.extend(re.findall(r'data-original=["\']([^"\']+)["\']', decoded))

        clean = []
        for url in urls:
            normalized = url.split('\\')[0].split('&quot;')[0].strip()
            if self._is_usable_image(normalized) and normalized not in clean:
                clean.append(normalized)
        return clean

    def _is_usable_image(self, url):
        if url in STOP_IMAGE_URLS:
            return False
        lowered = url.lower()
        if not any(lowered.endswith(ext) for ext in ('.jpg', '.jpeg', '.png', '.webp')):
            return False
        if '/-/empty/' in lowered or '/resize' in lowered:
            return False
        return not any(marker in lowered for marker in STOP_IMAGE_MARKERS)

    def _title_from_image_url(self, image_url, section_name, index):
        filename = image_url.rsplit('/', 1)[-1].rsplit('.', 1)[0]
        cleaned = re.sub(r'^\d+[-_ ]*', '', filename)
        cleaned = cleaned.replace('_', ' ').replace('-', ' ')
        cleaned = re.sub(r'\b\d+\b', ' ', cleaned)
        cleaned = re.sub(r'\b[a-f0-9]{8,}\b', ' ', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        if cleaned and re.search(r'[a-zа-я]{3,}', cleaned, flags=re.IGNORECASE):
            return cleaned.title()
        return f'Пример {index:02d}'

    def _product_name(self, section_name, title, index):
        title = self._clean_text(title)
        if not title:
            title = f'Пример {index:02d}'
        if title.lower() in section_name.lower():
            return section_name
        return f'{section_name} {title}'

    def _description(self, section, title, source_url):
        title = self._clean_text(title)
        detail = f' Дизайн/пример исполнения: {title}.' if title else ''
        return (
            f'{section["description"]}{detail} Изображение и название карточки взяты из публичного '
            f'раздела PRO SLIDE: {source_url}. Цена и складской остаток в DoorSkyStore заполнены как '
            'демо-данные магазина и редактируются через админку.'
        )

    def _clean_text(self, value):
        return re.sub(r'\s+', ' ', value or '').strip()

    def _dedupe_items(self, items):
        clean = []
        seen = set()
        for item in items:
            key = (item['title'].casefold(), item['image_url'])
            if key not in seen:
                seen.add(key)
                clean.append(item)
        return clean

    def _deactivate_stale_products(self, generated_skus):
        managed_prefixes = tuple(f'DSK-{prefix}-' for prefix in SOURCE_PREFIXES)
        stale_products = DoorProduct.objects.filter(sku__startswith='DSK-')
        for product in stale_products:
            if product.sku.startswith(managed_prefixes) and product.sku not in generated_skus:
                product.is_active = False
                product.save(update_fields=['is_active', 'updated_at'])
