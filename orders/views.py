from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from reports.documents import DOCUMENT_TYPES

from .forms import PaymentSimulationForm
from .models import Order, PaymentTransaction


def _has_order_access(request, order, public_key=None):
    has_public_key = public_key and order.public_key == public_key
    is_owner = request.user.is_authenticated and order.user_id == request.user.id
    has_staff_access = request.user.is_staff and request.user.has_perm('orders.view_order')
    return has_staff_access or is_owner or has_public_key


def order_detail(request, pk, public_key=None):
    order = get_object_or_404(
        Order.objects.prefetch_related('items__product', 'payment_transactions'),
        pk=pk,
    )
    if not _has_order_access(request, order, public_key):
        raise Http404

    documents = [
        {
            'type': document_type,
            'label': label,
            'pdf_url': reverse(
                'order_public_document_pdf',
                kwargs={'pk': order.pk, 'public_key': order.public_key, 'document_type': document_type},
            ),
            'download_url': (
                reverse(
                    'order_public_document_pdf',
                    kwargs={'pk': order.pk, 'public_key': order.public_key, 'document_type': document_type},
                )
                + '?download=1'
            ),
        }
        for document_type, label in DOCUMENT_TYPES
    ]
    package_url = reverse('order_public_documents_zip', kwargs={'pk': order.pk, 'public_key': order.public_key})
    return render(
        request,
        'orders/order_detail.html',
        {
            'order': order,
            'documents': documents,
            'package_url': package_url,
            'payment_url': order.get_payment_url(),
        },
    )


@require_http_methods(['GET', 'POST'])
def payment_simulation(request, pk, public_key=None):
    order = get_object_or_404(
        Order.objects.prefetch_related('items__product', 'payment_transactions'),
        pk=pk,
    )
    if not _has_order_access(request, order, public_key):
        raise Http404

    if order.is_paid:
        messages.info(request, f'Заказ #{order.pk} уже оплачен.')
        return redirect(order.get_absolute_url())

    if order.status == Order.STATUS_CANCELLED:
        messages.error(request, 'Отмененный заказ оплатить нельзя.')
        return redirect(order.get_absolute_url())

    form = PaymentSimulationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        reference = PaymentTransaction.make_reference(order)
        scenario = form.cleaned_data['scenario']
        now = timezone.now()
        payload = {
            'card_holder': form.cleaned_data.get('card_holder') or '',
            'card_last4': (form.cleaned_data.get('card_number') or '')[-4:],
            'payer_note': form.cleaned_data.get('payer_note') or '',
            'simulated_at': now.isoformat(),
        }

        if scenario == PaymentSimulationForm.SCENARIO_SUCCESS:
            transaction = PaymentTransaction.objects.create(
                order=order,
                amount=order.subtotal,
                method=order.payment_method,
                status=PaymentTransaction.STATUS_SUCCEEDED,
                reference=reference,
                payload=payload,
                processed_at=now,
            )
            order.mark_paid(
                reference=transaction.reference,
                paid_at=now,
                comment='Платеж проведен через DoorSky Pay Simulator.',
            )
            messages.success(request, f'Платеж {transaction.reference} проведен. Заказ переведен в работу.')
            return redirect(order.get_absolute_url())

        transaction = PaymentTransaction.objects.create(
            order=order,
            amount=order.subtotal,
            method=order.payment_method,
            status=PaymentTransaction.STATUS_FAILED,
            reference=reference,
            error_message='Сценарий симуляции: банк отклонил платеж.',
            payload=payload,
            processed_at=now,
        )
        order.mark_payment_failed('Платеж отклонен в симуляторе. Можно повторить попытку.')
        messages.error(request, f'Платеж {transaction.reference} отклонен. Попробуйте другой сценарий.')
        return redirect(order.get_payment_url())

    return render(request, 'orders/payment.html', {'order': order, 'form': form})
