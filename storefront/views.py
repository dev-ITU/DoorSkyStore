from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from catalog.models import Category, DoorProduct, StockItem
from orders.forms import CheckoutForm
from orders.models import Order, OrderItem

CART_SESSION_KEY = 'doorsky_cart'


def _cart_quantity_for_product(cart, product_id):
    try:
        return int(cart.get(str(product_id), 0))
    except (TypeError, ValueError):
        return 0


def _product_payload(product, cart=None):
    cart = cart or {}
    cart_quantity = _cart_quantity_for_product(cart, product.pk)
    remaining_quantity = max(product.available_quantity - cart_quantity, 0)
    return {
        'id': product.pk,
        'name': product.name,
        'slug': product.slug,
        'sku': product.sku,
        'category': {
            'name': product.category.name,
            'slug': product.category.slug,
        },
        'description': product.description,
        'price': str(product.price),
        'material': product.material,
        'color': product.color,
        'finish': product.finish,
        'opening_type': product.opening_type,
        'display_image': product.display_image,
        'available_quantity': product.available_quantity,
        'cart_quantity': cart_quantity,
        'remaining_quantity': remaining_quantity,
        'detail_url': product.get_absolute_url(),
    }


def _category_payload(category):
    return {
        'id': category.pk,
        'name': category.name,
        'slug': category.slug,
    }


def _option_payload(choices):
    return [{'value': value, 'label': label} for value, label in choices]


def _cart_item_payload(item):
    product = item['product']
    return {
        'product': {
            'id': product.pk,
            'name': product.name,
            'sku': product.sku,
            'category_name': product.category.name,
            'detail_url': product.get_absolute_url(),
        },
        'quantity': item['quantity'],
        'line_total': str(item['line_total']),
        'unit_price': str(product.price),
        'available_quantity': item['available_quantity'],
    }


def _cart(session):
    return session.get(CART_SESSION_KEY, {})


def _save_cart(session, cart):
    session[CART_SESSION_KEY] = {str(product_id): int(quantity) for product_id, quantity in cart.items() if int(quantity) > 0}
    session.modified = True


def _cart_items(session):
    cart = _cart(session)
    product_ids = [int(product_id) for product_id in cart.keys() if str(product_id).isdigit()]
    products = DoorProduct.objects.active().select_related('category', 'stock').filter(id__in=product_ids)
    product_map = {product.id: product for product in products}
    items = []
    subtotal = Decimal('0.00')

    for product_id_text, quantity in cart.items():
        if not str(product_id_text).isdigit():
            continue
        product_id = int(product_id_text)
        product = product_map.get(product_id)
        if not product:
            continue
        line_total = product.price * quantity
        subtotal += line_total
        items.append(
            {
                'product': product,
                'quantity': quantity,
                'line_total': line_total,
                'available_quantity': product.available_quantity,
            }
        )
    return items, subtotal


def _normalize_cart(session):
    cart = _cart(session)
    if not cart:
        return []

    product_ids = [int(product_id) for product_id in cart.keys() if str(product_id).isdigit()]
    products = DoorProduct.objects.active().select_related('stock').filter(id__in=product_ids)
    product_map = {product.id: product for product in products}
    normalized = {}
    adjustments = []

    for product_id_text, quantity in cart.items():
        if not str(product_id_text).isdigit():
            continue
        product_id = int(product_id_text)
        product = product_map.get(product_id)
        if not product:
            adjustments.append('Из корзины удален товар, который больше недоступен.')
            continue

        available_quantity = product.available_quantity
        if available_quantity <= 0:
            adjustments.append(f'«{product.name}» удален из корзины: товара нет в наличии.')
            continue

        safe_quantity = min(max(int(quantity), 1), available_quantity)
        if safe_quantity != int(quantity):
            adjustments.append(f'Количество «{product.name}» уменьшено до доступного остатка: {available_quantity} шт.')
        normalized[str(product.pk)] = safe_quantity

    if normalized != {str(product_id): int(quantity) for product_id, quantity in cart.items() if str(product_id).isdigit()}:
        _save_cart(session, normalized)
    return adjustments


def product_list(request):
    _normalize_cart(request.session)
    cart = _cart(request.session)
    products = list(DoorProduct.objects.active().select_related('category', 'stock')[:12])
    categories = list(Category.objects.filter(is_active=True))
    facets_queryset = DoorProduct.objects.active()
    materials = sorted(filter(None, facets_queryset.values_list('material', flat=True).distinct()))
    colors = sorted(filter(None, facets_queryset.values_list('color', flat=True).distinct()))
    context = {
        'products': products,
        'categories': categories,
        'materials': materials,
        'colors': colors,
        'opening_types': DoorProduct.OPENING_CHOICES,
        'catalog_props': {
            'apiUrl': reverse('product-list'),
            'addToCartUrl': reverse('add_to_cart'),
            'categories': [_category_payload(category) for category in categories],
            'materials': materials,
            'colors': colors,
            'openingTypes': _option_payload(DoorProduct.OPENING_CHOICES),
            'initialProducts': [_product_payload(product, cart) for product in products],
            'initialCount': facets_queryset.count(),
        },
    }
    return render(request, 'storefront/product_list.html', context)


def product_detail(request, slug):
    _normalize_cart(request.session)
    cart = _cart(request.session)
    product = get_object_or_404(
        DoorProduct.objects.active().select_related('category', 'stock'),
        slug=slug,
    )
    return render(
        request,
        'storefront/product_detail.html',
        {
            'product': product,
            'purchase_props': {
                'product': _product_payload(product, cart),
                'addToCartUrl': reverse('add_to_cart'),
            },
        },
    )


def cart_detail(request):
    adjustments = _normalize_cart(request.session)
    for adjustment in adjustments:
        messages.warning(request, adjustment)
    items, subtotal = _cart_items(request.session)
    return render(
        request,
        'storefront/cart.html',
        {
            'items': items,
            'subtotal': subtotal,
            'cart_props': {
                'initialItems': [_cart_item_payload(item) for item in items],
                'subtotal': str(subtotal),
                'catalogUrl': reverse('catalog'),
                'checkoutUrl': reverse('checkout'),
                'updateUrl': reverse('update_cart'),
            },
        },
    )


@require_POST
def add_to_cart(request):
    product = get_object_or_404(DoorProduct.objects.active().select_related('stock'), pk=request.POST.get('product_id'))
    try:
        quantity = max(int(request.POST.get('quantity', 1)), 1)
    except (TypeError, ValueError):
        quantity = 1

    cart = _cart(request.session)
    current_quantity = int(cart.get(str(product.pk), 0))
    remaining_quantity = max(product.available_quantity - current_quantity, 0)
    if remaining_quantity <= 0:
        message = f'В корзине уже весь доступный остаток: {product.available_quantity} шт.'
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse(
                {
                    'ok': False,
                    'message': message,
                    'product_id': product.pk,
                    'available_quantity': product.available_quantity,
                    'cart_quantity': current_quantity,
                    'remaining_quantity': 0,
                },
                status=400,
            )
        messages.error(request, message)
        return redirect(product.get_absolute_url())

    new_quantity = current_quantity + quantity
    if new_quantity > product.available_quantity:
        message = f'Можно добавить еще только {remaining_quantity} шт.'
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse(
                {
                    'ok': False,
                    'message': message,
                    'product_id': product.pk,
                    'available_quantity': product.available_quantity,
                    'cart_quantity': current_quantity,
                    'remaining_quantity': remaining_quantity,
                },
                status=400,
            )
        messages.error(request, message)
        return redirect(product.get_absolute_url())

    cart[str(product.pk)] = new_quantity
    _save_cart(request.session, cart)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse(
            {
                'ok': True,
                'cart_count': sum(cart.values()),
                'message': 'Товар добавлен в корзину.',
                'product_id': product.pk,
                'available_quantity': product.available_quantity,
                'cart_quantity': new_quantity,
                'remaining_quantity': max(product.available_quantity - new_quantity, 0),
            }
        )
    messages.success(request, 'Товар добавлен в корзину.')
    return redirect('cart')


@require_POST
def update_cart(request):
    cart = _cart(request.session)
    product_id = request.POST.get('product_id')
    try:
        quantity = int(request.POST.get('quantity', 0))
    except (TypeError, ValueError):
        quantity = 0

    if not product_id or not str(product_id).isdigit():
        return JsonResponse({'ok': False, 'message': 'Некорректный товар.'}, status=400)

    product = get_object_or_404(DoorProduct.objects.active().select_related('stock'), pk=product_id)
    update_message = 'Корзина обновлена.'
    if quantity <= 0:
        cart.pop(str(product.pk), None)
    elif quantity > product.available_quantity:
        if product.available_quantity <= 0:
            cart.pop(str(product.pk), None)
            update_message = f'«{product.name}» удален из корзины: товара нет в наличии.'
        else:
            cart[str(product.pk)] = product.available_quantity
            update_message = f'Количество уменьшено до доступного остатка: {product.available_quantity} шт.'
    else:
        cart[str(product.pk)] = quantity
    _save_cart(request.session, cart)

    items, subtotal = _cart_items(request.session)
    return JsonResponse(
        {
            'ok': True,
            'cart_count': sum(_cart(request.session).values()),
            'subtotal': str(subtotal),
            'items': [
                {
                    'product_id': item['product'].pk,
                    'quantity': item['quantity'],
                    'line_total': str(item['line_total']),
                    'available_quantity': item['available_quantity'],
                    'unit_price': str(item['product'].price),
                }
                for item in items
            ],
            'message': update_message,
        }
    )


def checkout(request):
    adjustments = _normalize_cart(request.session)
    for adjustment in adjustments:
        messages.warning(request, adjustment)
    items, subtotal = _cart_items(request.session)
    if not items:
        messages.info(request, 'Корзина пуста.')
        return redirect('catalog')

    form = CheckoutForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                order = Order.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    customer_name=form.cleaned_data['customer_name'],
                    customer_phone=form.cleaned_data['customer_phone'],
                    customer_email=form.cleaned_data['customer_email'],
                    customer_type=form.cleaned_data['customer_type'],
                    company_name=form.cleaned_data['company_name'],
                    company_inn=form.cleaned_data['company_inn'],
                    company_kpp=form.cleaned_data['company_kpp'],
                    company_address=form.cleaned_data['company_address'],
                    delivery_address=form.cleaned_data['delivery_address'],
                    payment_method=form.cleaned_data['payment_method'],
                    comment=form.cleaned_data['comment'],
                )
                for item in items:
                    product = DoorProduct.objects.get(pk=item['product'].pk)
                    stock = StockItem.objects.select_for_update().get(product=product)
                    if item['quantity'] > stock.available_quantity:
                        raise ValidationError(f'Недостаточно товара "{product.name}".')
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        quantity=item['quantity'],
                        unit_price=product.price,
                    )
                order.recalculate()
                order.reserve_stock(created_by=request.user if request.user.is_authenticated else None)
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if hasattr(exc, 'messages') else str(exc))
        else:
            _save_cart(request.session, {})
            messages.success(request, f'Заказ #{order.pk} создан. Товары зарезервированы.')
            if order.payment_method != Order.PAYMENT_CASH_ON_DELIVERY:
                return redirect(order.get_payment_url())
            return redirect(order.get_absolute_url())

    return render(request, 'storefront/checkout.html', {'form': form, 'items': items, 'subtotal': subtotal})


def robots_txt(request):
    sitemap_url = request.build_absolute_uri(reverse('sitemap'))
    lines = [
        'User-agent: *',
        'Allow: /',
        'Disallow: /admin/',
        'Disallow: /office/',
        'Disallow: /accounts/',
        'Disallow: /cart/',
        'Disallow: /checkout/',
        'Disallow: /orders/',
        'Disallow: /reports/',
        'Disallow: /api/',
        'Disallow: /_analytics/',
        f'Sitemap: {sitemap_url}',
        '',
    ]
    return HttpResponse('\n'.join(lines), content_type='text/plain; charset=utf-8')
