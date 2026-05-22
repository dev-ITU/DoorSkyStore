from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from orders.models import Order

from .forms import CustomerProfileForm, CustomerRegistrationForm, DeliveryAddressForm, EmailVerificationForm
from .models import DeliveryAddress
from .services import (
    get_customer_profile,
    send_email_verification_code,
    set_default_address,
    verify_email_code,
)


def _send_verification_message(request, user, resend=False):
    try:
        _, sent = send_email_verification_code(user, resend=resend)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
        return False
    except Exception:
        messages.error(request, 'Не удалось отправить код. Проверьте email или попробуйте позже.')
        return False

    if sent:
        messages.success(request, f'Код подтверждения отправлен на {user.email}.')
    else:
        messages.info(request, 'Активный код уже отправлен. Проверьте почту.')
    return True


def register(request):
    if request.user.is_authenticated:
        return redirect('account_dashboard')

    form = CustomerRegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, 'Аккаунт создан. Данные будут подставляться при следующих заказах.')
        _send_verification_message(request, user)
        return redirect('account_email_verify')

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
        'email_verified': profile.is_email_verified,
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
        if form.email_changed:
            _send_verification_message(request, request.user)
            messages.info(request, 'Email изменен. Подтвердите новый адрес кодом из письма.')
            return redirect('account_email_verify')
        messages.success(request, 'Данные покупателя сохранены.')
        return redirect('account_profile')
    return render(
        request,
        'customers/profile.html',
        {'form': form, 'profile': get_customer_profile(request.user)},
    )


@login_required
def email_verify(request):
    profile = get_customer_profile(request.user)
    if not request.user.email:
        messages.error(request, 'Сначала укажите email в профиле покупателя.')
        return redirect('account_profile')

    if profile.is_email_verified:
        messages.info(request, 'Email уже подтвержден.')
        return redirect('account_dashboard')

    form = EmailVerificationForm(request.POST or None)
    if request.method == 'POST' and request.POST.get('action') == 'resend':
        _send_verification_message(request, request.user, resend=True)
        return redirect('account_email_verify')

    if request.method == 'GET':
        _send_verification_message(request, request.user)

    if request.method == 'POST' and form.is_valid():
        try:
            verify_email_code(request.user, form.cleaned_data['code'])
        except ValidationError as exc:
            form.add_error('code', exc.messages[0])
        else:
            messages.success(request, 'Email подтвержден.')
            return redirect('account_dashboard')

    return render(request, 'customers/email_verify.html', {'form': form, 'profile': profile})


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
