from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Avg, Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from catalog.models import Category, DoorProduct, StockItem, StockMovement
from customers.models import EmailClientSettings
from customers.services import send_configured_email
from orders.models import Order, OrderItem, PaymentTransaction
from reports.documents import DOCUMENT_TYPES
from webanalytics.models import WebPageView, WebVisit

from .decorators import staff_required
from .forms import (
    BackofficeUserCreateForm,
    BackofficeUserEditForm,
    CategoryForm,
    EmailSettingsForm,
    OrderBackofficeForm,
    ProductForm,
    StockForm,
)


DEFAULT_GROUPS = {
    'DoorSky: администратор': [
        ('auth', 'user', 'add_user'),
        ('auth', 'user', 'change_user'),
        ('auth', 'user', 'view_user'),
        ('auth', 'group', 'change_group'),
        ('catalog', 'category', 'add_category'),
        ('catalog', 'category', 'change_category'),
        ('catalog', 'category', 'view_category'),
        ('catalog', 'doorproduct', 'add_doorproduct'),
        ('catalog', 'doorproduct', 'change_doorproduct'),
        ('catalog', 'doorproduct', 'view_doorproduct'),
        ('catalog', 'stockitem', 'change_stockitem'),
        ('catalog', 'stockitem', 'view_stockitem'),
        ('catalog', 'stockmovement', 'view_stockmovement'),
        ('orders', 'order', 'change_order'),
        ('orders', 'order', 'view_order'),
        ('orders', 'order', 'can_confirm_order'),
        ('orders', 'order', 'can_export_order_docs'),
        ('orders', 'order', 'can_simulate_payment'),
        ('orders', 'paymenttransaction', 'view_paymenttransaction'),
        ('webanalytics', 'webvisit', 'view_webvisit'),
        ('webanalytics', 'webpageview', 'view_webpageview'),
    ],
    'DoorSky: менеджер заказов': [
        ('orders', 'order', 'change_order'),
        ('orders', 'order', 'view_order'),
        ('orders', 'order', 'can_confirm_order'),
        ('orders', 'order', 'can_export_order_docs'),
        ('orders', 'order', 'can_simulate_payment'),
        ('orders', 'orderitem', 'view_orderitem'),
        ('orders', 'paymenttransaction', 'view_paymenttransaction'),
        ('catalog', 'doorproduct', 'view_doorproduct'),
        ('catalog', 'stockitem', 'view_stockitem'),
    ],
    'DoorSky: склад': [
        ('catalog', 'doorproduct', 'view_doorproduct'),
        ('catalog', 'stockitem', 'change_stockitem'),
        ('catalog', 'stockitem', 'view_stockitem'),
        ('catalog', 'stockmovement', 'add_stockmovement'),
        ('catalog', 'stockmovement', 'view_stockmovement'),
        ('orders', 'order', 'view_order'),
    ],
    'DoorSky: контент': [
        ('catalog', 'category', 'add_category'),
        ('catalog', 'category', 'change_category'),
        ('catalog', 'category', 'view_category'),
        ('catalog', 'doorproduct', 'add_doorproduct'),
        ('catalog', 'doorproduct', 'change_doorproduct'),
        ('catalog', 'doorproduct', 'view_doorproduct'),
        ('catalog', 'stockitem', 'change_stockitem'),
        ('catalog', 'stockitem', 'view_stockitem'),
    ],
    'DoorSky: аналитик': [
        ('catalog', 'category', 'view_category'),
        ('catalog', 'doorproduct', 'view_doorproduct'),
        ('catalog', 'stockitem', 'view_stockitem'),
        ('catalog', 'stockmovement', 'view_stockmovement'),
        ('orders', 'order', 'view_order'),
        ('orders', 'orderitem', 'view_orderitem'),
        ('orders', 'paymenttransaction', 'view_paymenttransaction'),
        ('webanalytics', 'webvisit', 'view_webvisit'),
        ('webanalytics', 'webpageview', 'view_webpageview'),
    ],
}


def _paginate(request, queryset, per_page=24):
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(request.GET.get('page'))


def _permission(app_label, model, codename):
    content_type = ContentType.objects.filter(app_label=app_label, model=model).first()
    if not content_type:
        return None
    return Permission.objects.filter(content_type=content_type, codename=codename).first()


def ensure_default_groups():
    for name, permission_specs in DEFAULT_GROUPS.items():
        group, _ = Group.objects.get_or_create(name=name)
        permissions = [
            permission
            for permission in (_permission(app_label, model, codename) for app_label, model, codename in permission_specs)
            if permission
        ]
        permission_ids = {permission.pk for permission in permissions}
        if set(group.permissions.values_list('pk', flat=True)) != permission_ids:
            group.permissions.set(permissions)


def _can_manage_users(user):
    return user.is_superuser or user.has_perm('auth.add_user') or user.has_perm('auth.change_user')


def _require_user_management(user):
    if not _can_manage_users(user):
        raise PermissionDenied('Недостаточно прав для управления пользователями.')


def _require_any_permission(user, *permissions):
    if user.is_superuser:
        return
    if any(user.has_perm(permission) for permission in permissions):
        return
    raise PermissionDenied('Недостаточно прав для этого действия.')


def _require_catalog_action_permission(user, action):
    if action == 'stock_update':
        _require_any_permission(user, 'catalog.change_stockitem')
        return
    if action == 'toggle_active':
        _require_any_permission(user, 'catalog.change_doorproduct')
        return
    raise PermissionDenied('Недостаточно прав для этого действия.')


def _require_order_action_permission(user, action):
    if action == 'save':
        _require_any_permission(user, 'orders.change_order')
        return
    if action in {'reserve', 'release', 'confirm', 'cancel'}:
        _require_any_permission(user, 'orders.can_confirm_order', 'orders.change_order')
        return
    if action in {'mark_paid', 'mark_failed'}:
        _require_any_permission(user, 'orders.can_simulate_payment', 'orders.change_order')
        return
    raise PermissionDenied('Недостаточно прав для этого действия.')


def _record_stock_changes(product, old_quantity, old_reserved, stock, user, reference='backoffice'):
    quantity_delta = stock.quantity - old_quantity
    reserved_delta = stock.reserved_quantity - old_reserved
    if quantity_delta:
        StockMovement.objects.create(
            product=product,
            movement_type=StockMovement.TYPE_ADJUSTMENT,
            quantity=quantity_delta,
            reference=reference,
            comment='Корректировка фактического остатка из панели управления.',
            created_by=user,
        )
    if reserved_delta:
        StockMovement.objects.create(
            product=product,
            movement_type=StockMovement.TYPE_RESERVE if reserved_delta > 0 else StockMovement.TYPE_RELEASE,
            quantity=reserved_delta,
            reference=reference,
            comment='Корректировка резерва из панели управления.',
            created_by=user,
        )


def _period_from_request(request):
    period = request.GET.get('period', '30')
    period_days = None if period == 'all' else 30
    if period in ('7', '30', '90', '365'):
        period_days = int(period)
    start_at = timezone.now() - timedelta(days=period_days) if period_days else None
    return period, start_at


def _width_rows(rows, value_key='count'):
    maximum = max((row.get(value_key) or 0 for row in rows), default=0)
    for row in rows:
        row['width'] = int(((row.get(value_key) or 0) / maximum) * 100) if maximum else 0
    return rows


def _dimension_rows(queryset, field_name, total, labels=None, limit=10):
    rows = list(queryset.values(field_name).annotate(count=Count('id')).order_by('-count', field_name)[:limit])
    for row in rows:
        raw_label = row.get(field_name) or 'Не определено'
        row['label'] = labels.get(raw_label, raw_label) if labels else raw_label
        row['share'] = round((row['count'] / total) * 100, 1) if total else 0
    return _width_rows(rows)


@staff_required
def dashboard(request):
    ensure_default_groups()
    _require_any_permission(
        request.user,
        'orders.view_order',
        'catalog.view_doorproduct',
        'catalog.view_stockitem',
        'webanalytics.view_webvisit',
        'auth.view_user',
    )
    orders = Order.objects.prefetch_related('items')
    paid_orders = orders.filter(payment_status=Order.PAYMENT_PAID).exclude(status=Order.STATUS_CANCELLED)
    low_stock = StockItem.objects.select_related('product', 'product__category').filter(
        quantity__lte=F('reserved_quantity') + F('min_quantity')
    )
    context = {
        'orders_total': orders.count(),
        'orders_new': orders.filter(status=Order.STATUS_NEW).count(),
        'orders_in_progress': orders.filter(status=Order.STATUS_IN_PROGRESS).count(),
        'orders_paid': paid_orders.count(),
        'revenue': paid_orders.aggregate(total=Sum('subtotal'))['total'] or 0,
        'products_total': DoorProduct.objects.count(),
        'products_active': DoorProduct.objects.filter(is_active=True).count(),
        'low_stock_count': low_stock.count(),
        'recent_orders': orders.select_related('manager')[:8],
        'low_stock': low_stock[:8],
        'recent_movements': StockMovement.objects.select_related('product', 'created_by')[:8],
    }
    return render(request, 'backoffice/dashboard.html', context)


@staff_required
def analytics(request):
    _require_any_permission(request.user, 'orders.view_order', 'catalog.view_stockitem')
    period, start_at = _period_from_request(request)

    orders = Order.objects.all()
    if start_at:
        orders = orders.filter(created_at__gte=start_at)
    paid_orders = orders.filter(payment_status=Order.PAYMENT_PAID).exclude(status=Order.STATUS_CANCELLED)
    order_items = OrderItem.objects.filter(order__in=orders).select_related('product', 'product__category')
    line_total = ExpressionWrapper(
        F('quantity') * F('unit_price'),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )

    total_orders = orders.count()
    paid_count = paid_orders.count()
    revenue = paid_orders.aggregate(total=Sum('subtotal'))['total'] or 0
    average_order = paid_orders.aggregate(avg=Avg('subtotal'))['avg'] or 0
    products_sold = order_items.filter(order__payment_status=Order.PAYMENT_PAID).aggregate(total=Sum('quantity'))[
        'total'
    ] or 0
    conversion = round((paid_count / total_orders) * 100, 1) if total_orders else 0

    daily_raw = list(
        orders.annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(
            orders_count=Count('id'),
            revenue=Sum('subtotal', filter=Q(payment_status=Order.PAYMENT_PAID)),
        )
        .order_by('day')
    )
    max_daily_revenue = max((row['revenue'] or 0 for row in daily_raw), default=0)
    max_daily_orders = max((row['orders_count'] or 0 for row in daily_raw), default=0)
    daily_rows = [
        {
            **row,
            'revenue_width': int(((row['revenue'] or 0) / max_daily_revenue) * 100) if max_daily_revenue else 0,
            'orders_width': int(((row['orders_count'] or 0) / max_daily_orders) * 100) if max_daily_orders else 0,
        }
        for row in daily_raw
    ]

    status_labels = dict(Order.STATUS_CHOICES)
    payment_labels = dict(Order.PAYMENT_STATUS_CHOICES)
    payment_method_labels = dict(Order.PAYMENT_METHOD_CHOICES)
    customer_type_labels = dict(Order.CUSTOMER_TYPE_CHOICES)
    status_rows = [
        {
            **row,
            'label': status_labels.get(row['status'], row['status']),
            'width': int((row['count'] / total_orders) * 100) if total_orders else 0,
        }
        for row in orders.values('status').annotate(count=Count('id'), total=Sum('subtotal')).order_by('status')
    ]
    payment_rows = [
        {
            **row,
            'label': payment_labels.get(row['payment_status'], row['payment_status']),
            'width': int((row['count'] / total_orders) * 100) if total_orders else 0,
        }
        for row in orders.values('payment_status')
        .annotate(count=Count('id'), total=Sum('subtotal'))
        .order_by('payment_status')
    ]
    payment_method_rows = [
        {
            **row,
            'label': payment_method_labels.get(row['payment_method'], row['payment_method']),
            'width': int((row['count'] / total_orders) * 100) if total_orders else 0,
        }
        for row in orders.values('payment_method')
        .annotate(count=Count('id'), total=Sum('subtotal'))
        .order_by('payment_method')
    ]
    customer_rows = [
        {
            **row,
            'label': customer_type_labels.get(row['customer_type'], row['customer_type']),
            'width': int((row['count'] / total_orders) * 100) if total_orders else 0,
        }
        for row in orders.values('customer_type')
        .annotate(count=Count('id'), total=Sum('subtotal'))
        .order_by('customer_type')
    ]

    top_products = list(
        order_items.filter(order__payment_status=Order.PAYMENT_PAID)
        .annotate(line_total=line_total)
        .values('product__name', 'product__sku')
        .annotate(quantity=Sum('quantity'), revenue=Sum('line_total'))
        .order_by('-revenue')[:10]
    )
    max_product_revenue = max((row['revenue'] or 0 for row in top_products), default=0)
    for row in top_products:
        row['width'] = int(((row['revenue'] or 0) / max_product_revenue) * 100) if max_product_revenue else 0

    category_sales = list(
        order_items.filter(order__payment_status=Order.PAYMENT_PAID)
        .annotate(line_total=line_total)
        .values('product__category__name')
        .annotate(quantity=Sum('quantity'), revenue=Sum('line_total'), orders_count=Count('order', distinct=True))
        .order_by('-revenue')[:10]
    )
    max_category_revenue = max((row['revenue'] or 0 for row in category_sales), default=0)
    for row in category_sales:
        row['width'] = int(((row['revenue'] or 0) / max_category_revenue) * 100) if max_category_revenue else 0

    stock_totals = StockItem.objects.aggregate(
        quantity=Sum('quantity'),
        reserved=Sum('reserved_quantity'),
        minimum=Sum('min_quantity'),
    )
    total_quantity = stock_totals['quantity'] or 0
    total_reserved = stock_totals['reserved'] or 0
    stock_context = {
        'quantity': total_quantity,
        'reserved': total_reserved,
        'available': max(total_quantity - total_reserved, 0),
        'minimum': stock_totals['minimum'] or 0,
        'low_count': StockItem.objects.filter(quantity__lte=F('reserved_quantity') + F('min_quantity')).count(),
        'empty_count': StockItem.objects.filter(quantity__lte=0).count(),
    }
    category_stock = list(StockItem.objects.values('product__category__name').annotate(
        products=Count('product'),
        quantity=Sum('quantity'),
        reserved=Sum('reserved_quantity'),
    ).order_by('product__category__name'))
    for row in category_stock:
        row['available'] = max((row['quantity'] or 0) - (row['reserved'] or 0), 0)

    return render(
        request,
        'backoffice/analytics.html',
        {
            'period': period,
            'period_choices': (
                ('7', '7 дней'),
                ('30', '30 дней'),
                ('90', '90 дней'),
                ('365', 'Год'),
                ('all', 'Все время'),
            ),
            'total_orders': total_orders,
            'paid_count': paid_count,
            'revenue': revenue,
            'average_order': average_order,
            'products_sold': products_sold,
            'conversion': conversion,
            'daily_rows': daily_rows,
            'status_rows': status_rows,
            'payment_rows': payment_rows,
            'payment_method_rows': payment_method_rows,
            'customer_rows': customer_rows,
            'top_products': top_products,
            'category_sales': category_sales,
            'stock': stock_context,
            'category_stock': category_stock,
        },
    )


@staff_required
def web_analytics(request):
    ensure_default_groups()
    _require_any_permission(request.user, 'webanalytics.view_webvisit', 'webanalytics.view_webpageview')
    period, start_at = _period_from_request(request)
    visits = WebVisit.objects.all()
    page_views = WebPageView.objects.select_related('visit', 'user')
    if start_at:
        visits = visits.filter(started_at__gte=start_at)
        page_views = page_views.filter(created_at__gte=start_at)

    total_views = page_views.count()
    total_visits = visits.count()
    unique_visitors = visits.values('visitor_id').distinct().count()
    known_users = visits.exclude(user__isnull=True).values('user').distinct().count()
    bounces = visits.filter(page_views_count__lte=1).count()
    bounce_rate = round((bounces / total_visits) * 100, 1) if total_visits else 0
    views_per_visit = round(total_views / total_visits, 1) if total_visits else 0
    avg_engagement = page_views.aggregate(avg=Avg('engagement_seconds'))['avg'] or 0
    returning_visitors = 0
    if start_at and unique_visitors:
        returning_visitors = (
            WebVisit.objects.filter(visitor_id__in=visits.values_list('visitor_id', flat=True), started_at__lt=start_at)
            .values('visitor_id')
            .distinct()
            .count()
        )

    daily_rows = list(
        page_views.annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(
            views_count=Count('id'),
            visits_count=Count('visit', distinct=True),
            visitors_count=Count('visit__visitor_id', distinct=True),
        )
        .order_by('day')
    )
    max_views = max((row['views_count'] for row in daily_rows), default=0)
    max_visits = max((row['visits_count'] for row in daily_rows), default=0)
    for row in daily_rows:
        row['views_width'] = int((row['views_count'] / max_views) * 100) if max_views else 0
        row['visits_width'] = int((row['visits_count'] / max_visits) * 100) if max_visits else 0

    top_pages = list(
        page_views.values('path')
        .annotate(count=Count('id'), visits=Count('visit', distinct=True), avg_engagement=Avg('engagement_seconds'))
        .order_by('-count')[:12]
    )
    _width_rows(top_pages)

    country_rows = _dimension_rows(visits, 'country', total_visits, limit=12)
    city_rows = list(visits.values('city', 'country').annotate(count=Count('id')).order_by('-count', 'city')[:12])
    for row in city_rows:
        city = row['city'] or 'Не определено'
        country = row['country'] or ''
        row['label'] = f'{city}, {country}' if country and city != 'Не определено' else city
        row['share'] = round((row['count'] / total_visits) * 100, 1) if total_visits else 0
    _width_rows(city_rows)

    device_labels = dict(WebVisit.DEVICE_CHOICES)
    channel_labels = dict(WebVisit.CHANNEL_CHOICES)
    device_type_rows = _dimension_rows(visits, 'device_type', total_visits, device_labels)
    device_rows = _dimension_rows(visits, 'device', total_visits)
    browser_rows = _dimension_rows(visits, 'browser', total_visits)
    os_rows = _dimension_rows(visits, 'os', total_visits)
    channel_rows = _dimension_rows(visits, 'traffic_channel', total_visits, channel_labels)
    referrer_rows = _dimension_rows(visits.exclude(referrer_domain=''), 'referrer_domain', total_visits)
    utm_source_rows = _dimension_rows(visits.exclude(utm_source=''), 'utm_source', total_visits)
    utm_campaign_rows = _dimension_rows(visits.exclude(utm_campaign=''), 'utm_campaign', total_visits)
    landing_rows = _dimension_rows(visits, 'landing_path', total_visits)
    exit_rows = _dimension_rows(visits, 'exit_path', total_visits)

    screen_rows = list(
        page_views.exclude(viewport_width__isnull=True)
        .values('viewport_width', 'viewport_height')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )
    for row in screen_rows:
        row['label'] = f'{row["viewport_width"]}x{row["viewport_height"]}'
        row['share'] = round((row['count'] / total_views) * 100, 1) if total_views else 0
    _width_rows(screen_rows)

    funnel_rows = [
        {'label': 'Каталог', 'count': page_views.filter(path='/').count()},
        {'label': 'Карточки товаров', 'count': page_views.filter(path__startswith='/catalog/').count()},
        {'label': 'Корзина', 'count': page_views.filter(path__startswith='/cart/').count()},
        {'label': 'Оформление', 'count': page_views.filter(path__startswith='/checkout/').count()},
        {'label': 'Страницы заказа', 'count': page_views.filter(path__startswith='/orders/').count()},
    ]
    order_queryset = Order.objects.all()
    if start_at:
        order_queryset = order_queryset.filter(created_at__gte=start_at)
    funnel_rows.extend(
        [
            {'label': 'Созданные заказы', 'count': order_queryset.count()},
            {'label': 'Оплаченные заказы', 'count': order_queryset.filter(payment_status=Order.PAYMENT_PAID).count()},
        ]
    )
    _width_rows(funnel_rows)

    latest_views = page_views.order_by('-created_at')[:20]

    return render(
        request,
        'backoffice/web_analytics.html',
        {
            'period': period,
            'period_choices': (
                ('7', '7 дней'),
                ('30', '30 дней'),
                ('90', '90 дней'),
                ('365', 'Год'),
                ('all', 'Все время'),
            ),
            'total_views': total_views,
            'total_visits': total_visits,
            'unique_visitors': unique_visitors,
            'known_users': known_users,
            'returning_visitors': returning_visitors,
            'bounce_rate': bounce_rate,
            'views_per_visit': views_per_visit,
            'avg_engagement': avg_engagement,
            'daily_rows': daily_rows,
            'top_pages': top_pages,
            'country_rows': country_rows,
            'city_rows': city_rows,
            'device_type_rows': device_type_rows,
            'device_rows': device_rows,
            'browser_rows': browser_rows,
            'os_rows': os_rows,
            'channel_rows': channel_rows,
            'referrer_rows': referrer_rows,
            'utm_source_rows': utm_source_rows,
            'utm_campaign_rows': utm_campaign_rows,
            'landing_rows': landing_rows,
            'exit_rows': exit_rows,
            'screen_rows': screen_rows,
            'funnel_rows': funnel_rows,
            'latest_views': latest_views,
        },
    )


@staff_required
def orders_list(request):
    _require_any_permission(request.user, 'orders.view_order')
    queryset = Order.objects.select_related('manager').prefetch_related('items').order_by('-created_at')
    status = request.GET.get('status', '')
    payment_status = request.GET.get('payment_status', '')
    query = request.GET.get('q', '').strip()

    if status:
        queryset = queryset.filter(status=status)
    if payment_status:
        queryset = queryset.filter(payment_status=payment_status)
    if query:
        filters = (
            Q(customer_name__icontains=query)
            | Q(customer_phone__icontains=query)
            | Q(customer_email__icontains=query)
            | Q(payment_reference__icontains=query)
        )
        if query.isdigit():
            filters |= Q(pk=int(query))
        queryset = queryset.filter(filters)

    return render(
        request,
        'backoffice/orders.html',
        {
            'page_obj': _paginate(request, queryset, 20),
            'status_choices': Order.STATUS_CHOICES,
            'payment_status_choices': Order.PAYMENT_STATUS_CHOICES,
            'current_status': status,
            'current_payment_status': payment_status,
            'query': query,
        },
    )


@staff_required
@require_http_methods(['GET', 'POST'])
def order_detail(request, pk):
    order = get_object_or_404(
        Order.objects.select_related('manager').prefetch_related('items__product__category', 'payment_transactions'),
        pk=pk,
    )

    _require_any_permission(request.user, 'orders.view_order')
    if request.method == 'POST':
        action = request.POST.get('action', 'save')
        _require_order_action_permission(request.user, action)
        if action == 'save':
            form = OrderBackofficeForm(request.POST, instance=order)
            if form.is_valid():
                form.save()
                messages.success(request, f'Заказ #{order.pk} обновлен.')
                return redirect('backoffice_order_detail', pk=order.pk)
        else:
            try:
                _handle_order_action(order, action, request.user)
                messages.success(request, f'Действие по заказу #{order.pk} выполнено.')
            except ValidationError as exc:
                messages.error(request, f'Заказ #{order.pk}: {exc}')
            return redirect('backoffice_order_detail', pk=order.pk)
    else:
        form = OrderBackofficeForm(instance=order)

    documents = [
        {
            'label': label,
            'pdf_url': reverse('order_document_pdf', kwargs={'pk': order.pk, 'document_type': document_type}),
            'download_url': reverse('order_document_pdf', kwargs={'pk': order.pk, 'document_type': document_type})
            + '?download=1',
        }
        for document_type, label in DOCUMENT_TYPES
    ]

    return render(
        request,
        'backoffice/order_detail.html',
        {
            'order': order,
            'form': form,
            'documents': documents,
            'package_url': reverse('order_documents_zip', kwargs={'pk': order.pk}),
        },
    )


def _handle_order_action(order, action, user):
    if action == 'reserve':
        order.reserve_stock(created_by=user)
        return
    if action == 'release':
        order.release_stock(created_by=user)
        return
    if action == 'confirm':
        order.confirm(manager=user)
        return
    if action == 'cancel':
        order.cancel(user=user)
        return
    if action == 'mark_paid':
        if order.is_paid:
            raise ValidationError('Заказ уже оплачен.')
        if order.status == Order.STATUS_CANCELLED:
            raise ValidationError('Отмененный заказ нельзя оплатить.')
        now = timezone.now()
        transaction = PaymentTransaction.objects.create(
            order=order,
            amount=order.subtotal,
            method=order.payment_method,
            status=PaymentTransaction.STATUS_SUCCEEDED,
            reference=PaymentTransaction.make_reference(order),
            payload={'source': 'backoffice', 'user_id': user.pk},
            processed_at=now,
        )
        order.mark_paid(
            reference=transaction.reference,
            paid_at=now,
            comment=f'Платеж проведен менеджером {user.get_username()} из панели управления.',
        )
        return
    if action == 'mark_failed':
        if order.is_paid:
            raise ValidationError('Оплаченный заказ нельзя перевести в отказ.')
        PaymentTransaction.objects.create(
            order=order,
            amount=order.subtotal,
            method=order.payment_method,
            status=PaymentTransaction.STATUS_FAILED,
            reference=PaymentTransaction.make_reference(order),
            error_message='Отказ оплаты из панели управления.',
            payload={'source': 'backoffice', 'user_id': user.pk},
            processed_at=timezone.now(),
        )
        order.mark_payment_failed(f'Платеж отклонен менеджером {user.get_username()} из панели управления.')
        return
    raise ValidationError('Неизвестное действие.')


@staff_required
@require_http_methods(['GET', 'POST'])
def catalog_list(request):
    if request.method == 'POST':
        _require_catalog_action_permission(request.user, request.POST.get('action'))
        _handle_catalog_post(request)
        return redirect(request.POST.get('next') or 'backoffice_catalog')

    _require_any_permission(request.user, 'catalog.view_doorproduct', 'catalog.change_doorproduct')
    queryset = DoorProduct.objects.select_related('category', 'stock').order_by('category__name', 'name')
    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '')
    active = request.GET.get('active', '')
    stock_state = request.GET.get('stock_state', '')

    if query:
        queryset = queryset.filter(
            Q(name__icontains=query)
            | Q(sku__icontains=query)
            | Q(description__icontains=query)
            | Q(material__icontains=query)
            | Q(color__icontains=query)
        )
    if category:
        queryset = queryset.filter(category_id=category)
    if active in ('1', '0'):
        queryset = queryset.filter(is_active=active == '1')
    if stock_state == 'low':
        queryset = queryset.filter(stock__quantity__lte=F('stock__reserved_quantity') + F('stock__min_quantity'))
    elif stock_state == 'empty':
        queryset = queryset.filter(stock__quantity__lte=0)

    return render(
        request,
        'backoffice/catalog.html',
        {
            'page_obj': _paginate(request, queryset, 24),
            'categories': Category.objects.order_by('name'),
            'query': query,
            'current_category': category,
            'current_active': active,
            'current_stock_state': stock_state,
        },
    )


def _handle_catalog_post(request):
    product = get_object_or_404(DoorProduct.objects.select_related('stock'), pk=request.POST.get('product_id'))
    action = request.POST.get('action')
    if action == 'toggle_active':
        product.is_active = not product.is_active
        product.save(update_fields=['is_active', 'updated_at'])
        messages.success(request, f'Товар {product.sku} {"включен" if product.is_active else "скрыт"}.')
        return
    if action == 'stock_update':
        stock, _ = StockItem.objects.get_or_create(product=product)
        old_quantity = stock.quantity
        old_reserved = stock.reserved_quantity
        try:
            stock.quantity = max(int(request.POST.get('quantity', stock.quantity)), 0)
            stock.reserved_quantity = max(int(request.POST.get('reserved_quantity', stock.reserved_quantity)), 0)
            stock.min_quantity = max(int(request.POST.get('min_quantity', stock.min_quantity)), 0)
            stock.full_clean()
            stock.save()
            _record_stock_changes(product, old_quantity, old_reserved, stock, request.user, reference='backoffice:list')
            messages.success(request, f'Остатки {product.sku} обновлены.')
        except (TypeError, ValueError, ValidationError) as exc:
            messages.error(request, f'{product.sku}: {exc}')
        return
    messages.error(request, 'Неизвестное действие каталога.')


@staff_required
@require_http_methods(['GET', 'POST'])
def product_create(request):
    _require_any_permission(request.user, 'catalog.add_doorproduct')
    return _product_form(request, None)


@staff_required
@require_http_methods(['GET', 'POST'])
def product_edit(request, pk):
    _require_any_permission(request.user, 'catalog.change_doorproduct')
    product = get_object_or_404(DoorProduct.objects.select_related('stock'), pk=pk)
    return _product_form(request, product)


def _product_form(request, product):
    is_create = product is None
    stock = None if is_create else getattr(product, 'stock', None)
    if stock is None:
        stock = StockItem(product=product) if product else StockItem()

    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    stock_form = StockForm(request.POST or None, instance=stock)

    if request.method == 'POST' and form.is_valid() and stock_form.is_valid():
        product = form.save()
        old_quantity = 0 if is_create or not stock.pk else StockItem.objects.get(pk=stock.pk).quantity
        old_reserved = 0 if is_create or not stock.pk else StockItem.objects.get(pk=stock.pk).reserved_quantity
        stock = stock_form.save(commit=False)
        stock.product = product
        stock.full_clean()
        stock.save()
        _record_stock_changes(product, old_quantity, old_reserved, stock, request.user, reference='backoffice:product')
        messages.success(request, f'Товар {product.sku} сохранен.')
        return redirect('backoffice_product_edit', pk=product.pk)

    return render(
        request,
        'backoffice/product_form.html',
        {
            'form': form,
            'stock_form': stock_form,
            'product': product,
            'is_create': is_create,
        },
    )


@staff_required
@require_http_methods(['GET', 'POST'])
def categories(request):
    if request.method == 'POST':
        _require_any_permission(request.user, 'catalog.add_category')
    else:
        _require_any_permission(request.user, 'catalog.view_category', 'catalog.change_category')
    form = CategoryForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        category = form.save()
        messages.success(request, f'Категория {category.name} сохранена.')
        return redirect('backoffice_categories')

    return render(
        request,
        'backoffice/categories.html',
        {
            'form': form,
            'categories': Category.objects.annotate(products_count=Count('products')).order_by('name'),
        },
    )


@staff_required
@require_http_methods(['GET', 'POST'])
def email_settings(request):
    if not request.user.is_superuser:
        raise PermissionDenied('Настройки почты доступны только суперпользователю.')

    email_config = EmailClientSettings.get_solo()
    form = EmailSettingsForm(request.POST or None, instance=email_config)
    if request.method == 'POST' and form.is_valid():
        email_config = form.save(updated_by=request.user)
        if request.POST.get('action') == 'send_test':
            test_email = form.cleaned_data['test_email']
            try:
                send_configured_email(
                    subject='Тестовая отправка DoorSky',
                    message=(
                        'Это тестовое письмо из панели DoorSky.\n\n'
                        f'Время отправки: {timezone.localtime(timezone.now()):%d.%m.%Y %H:%M}.'
                    ),
                    recipient_list=[test_email],
                )
            except Exception as exc:
                messages.error(request, f'Настройки сохранены, но тестовое письмо не отправлено: {exc}')
            else:
                messages.success(request, f'Настройки сохранены. Тестовое письмо отправлено на {test_email}.')
        else:
            messages.success(request, 'Настройки почты сохранены.')
        return redirect('backoffice_email_settings')

    return render(
        request,
        'backoffice/email_settings.html',
        {
            'form': form,
            'email_config': email_config,
        },
    )


@staff_required
def users_list(request):
    _require_user_management(request.user)
    ensure_default_groups()
    query = request.GET.get('q', '').strip()
    queryset = get_user_model().objects.prefetch_related('groups').order_by('username')
    if query:
        queryset = queryset.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )
    return render(
        request,
        'backoffice/users.html',
        {
            'page_obj': _paginate(request, queryset, 24),
            'query': query,
            'groups': Group.objects.order_by('name'),
        },
    )


@staff_required
@require_http_methods(['GET', 'POST'])
def user_create(request):
    _require_user_management(request.user)
    ensure_default_groups()
    form = BackofficeUserCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        messages.success(request, f'Пользователь {user.username} создан.')
        return redirect('backoffice_user_edit', pk=user.pk)
    return render(
        request,
        'backoffice/user_form.html',
        {
            'form': form,
            'managed_user': None,
            'is_create': True,
            'groups': Group.objects.order_by('name'),
        },
    )


@staff_required
@require_http_methods(['GET', 'POST'])
def user_edit(request, pk):
    _require_user_management(request.user)
    ensure_default_groups()
    managed_user = get_object_or_404(get_user_model().objects.prefetch_related('groups', 'user_permissions'), pk=pk)
    form = BackofficeUserEditForm(request.POST or None, instance=managed_user)
    if request.method == 'POST' and form.is_valid():
        if managed_user.pk == request.user.pk and not form.cleaned_data.get('is_staff'):
            form.add_error('is_staff', 'Нельзя снять у себя доступ в панель.')
        elif managed_user.pk == request.user.pk and not form.cleaned_data.get('is_active'):
            form.add_error('is_active', 'Нельзя отключить свою учетную запись.')
        else:
            user = form.save()
            messages.success(request, f'Права пользователя {user.username} обновлены.')
            return redirect('backoffice_user_edit', pk=user.pk)
    return render(
        request,
        'backoffice/user_form.html',
        {
            'form': form,
            'managed_user': managed_user,
            'is_create': False,
            'groups': Group.objects.order_by('name'),
        },
    )
