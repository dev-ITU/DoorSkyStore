from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from orders.models import Order

from .forms import CustomerProfileForm, CustomerRegistrationForm, DeliveryAddressForm
from .models import DeliveryAddress
from .services import get_customer_profile, set_default_address


def register(request):
    if request.user.is_authenticated:
        return redirect('account_dashboard')

    form = CustomerRegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, 'Аккаунт создан. Данные будут подставляться при следующих заказах.')
        return redirect('account_dashboard')

    return render(request, 'customers/register.html', {'form': form})


@login_required
def dashboard(request):
    profile = get_customer_profile(request.user)
    orders = (
        Order.objects.filter(user=request.user)
        .prefetch_related('items__product')
        .order_by('-created_at')
    )
    context = {
        'profile': profile,
        'orders_total': orders.count(),
        'orders_paid': orders.filter(payment_status=Order.PAYMENT_PAID).count(),
        'orders_active': orders.exclude(status__in=[Order.STATUS_COMPLETED, Order.STATUS_CANCELLED]).count(),
        'recent_orders': orders[:5],
        'addresses_total': request.user.delivery_addresses.count(),
        'addresses': request.user.delivery_addresses.all()[:4],
    }
    return render(request, 'customers/dashboard.html', context)


@login_required
def profile(request):
    form = CustomerProfileForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Данные покупателя сохранены.')
        return redirect('account_profile')
    return render(request, 'customers/profile.html', {'form': form})


@login_required
def orders(request):
    user_orders = (
        Order.objects.filter(user=request.user)
        .prefetch_related('items__product')
        .order_by('-created_at')
    )
    return render(request, 'customers/orders.html', {'orders': user_orders})


@login_required
def addresses(request):
    return render(
        request,
        'customers/addresses.html',
        {'addresses': request.user.delivery_addresses.all()},
    )


@login_required
def address_create(request):
    form = DeliveryAddressForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Адрес доставки добавлен.')
        return redirect('account_addresses')
    return render(request, 'customers/address_form.html', {'form': form, 'title': 'Новый адрес'})


@login_required
def address_edit(request, pk):
    address = get_object_or_404(DeliveryAddress, pk=pk, user=request.user)
    form = DeliveryAddressForm(request.POST or None, instance=address, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Адрес доставки обновлен.')
        return redirect('account_addresses')
    return render(request, 'customers/address_form.html', {'form': form, 'title': 'Редактировать адрес'})


@login_required
@require_POST
def address_delete(request, pk):
    address = get_object_or_404(DeliveryAddress, pk=pk, user=request.user)
    was_default = address.is_default
    address.delete()
    if was_default:
        next_address = request.user.delivery_addresses.first()
        if next_address:
            set_default_address(request.user, next_address)
    messages.success(request, 'Адрес доставки удален.')
    return redirect('account_addresses')
