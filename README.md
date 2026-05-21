# DoorSkyStore

Информационная система интернет-магазина дверей "Дорскай" на Django, DRF и PostgreSQL.

## Возможности

- Каталог дверей с категориями, характеристиками, ценами и остатками.
- React Islands для каталога, корзины и покупки с AJAX-фильтрами.
- Корзина и оформление заказа с контролем доступного количества.
- Резервирование склада при создании заказа и списание при подтверждении.
- Кастомная панель `/office/` вместо стандартной админки: заказы, каталог, склад, пользователи, роли и права.
- Ролевое разделение через группы `DoorSky: администратор`, `DoorSky: менеджер заказов`, `DoorSky: склад`, `DoorSky: контент`, `DoorSky: аналитик`.
- DRF API для каталога: `/api/products/`, `/api/categories/`.
- XLSX-отчеты по продажам и складу.
- PDF-документы заказа: заказ, счет, чек, накладная, акт, ZIP-пакет.
- Веб-аналитика: визиты, просмотры, устройства, браузеры, ОС, гео, источники, UTM и воронка.
- Автоматические `/sitemap.xml` и `/robots.txt`.
- Seed-данные на основе публичной структуры каталога PRO SLIDE.

## Локальный запуск без Docker

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
python manage.py migrate
python manage.py seed_roles
python manage.py seed_proslide
python manage.py createsuperuser
python manage.py runserver
```

## Production checklist

Перед запуском в production задайте переменные окружения:

```bash
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=<длинный случайный ключ>
DJANGO_ALLOWED_HOSTS=doorsky.example.com,www.doorsky.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://doorsky.example.com,https://www.doorsky.example.com
DJANGO_SECURE_SSL_REDIRECT=1
DJANGO_SECURE_HSTS_SECONDS=31536000
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=1
DJANGO_SECURE_HSTS_PRELOAD=1
DJANGO_SESSION_COOKIE_SECURE=1
DJANGO_CSRF_COOKIE_SECURE=1
```

Проверка:

```bash
DJANGO_DEBUG=0 DJANGO_SECRET_KEY=<ключ> DJANGO_ALLOWED_HOSTS=doorsky.example.com DJANGO_CSRF_TRUSTED_ORIGINS=https://doorsky.example.com python manage.py check --deploy
python manage.py test
```

## Запуск в Docker

```bash
cp .env.example .env
docker compose up --build
```

Для разработки React-островов можно отдельно запустить watcher:

```bash
docker compose up frontend
```

После старта выполните seed-команды внутри контейнера:

```bash
docker compose exec web python manage.py seed_roles
docker compose exec web python manage.py seed_proslide
docker compose exec web python manage.py createsuperuser
```
