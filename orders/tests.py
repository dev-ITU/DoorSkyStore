from io import BytesIO
from zipfile import ZipFile

from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, DoorProduct, StockItem
from .models import Order, OrderItem, PaymentTransaction


class OrderStockTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name='Скрытые двери', slug='hidden')
        self.product = DoorProduct.objects.create(
            category=category,
            name='Modul-60',
            slug='modul-60',
            sku='DSK-STOCK-1',
            price=75000,
            material='Алюминий / МДФ',
            color='Под покраску',
            finish='Грунт',
            opening_type=DoorProduct.OPENING_HIDDEN,
        )
        self.stock = StockItem.objects.create(product=self.product, quantity=5, reserved_quantity=0)

    def test_order_reserves_and_confirms_stock(self):
        order = Order.objects.create(customer_name='Иван', customer_phone='+79990000000')
        OrderItem.objects.create(order=order, product=self.product, quantity=2, unit_price=self.product.price)
        order.recalculate()

        order.reserve_stock()
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 5)
        self.assertEqual(self.stock.reserved_quantity, 2)
        self.assertEqual(self.stock.available_quantity, 3)

        order.confirm()
        self.stock.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CONFIRMED)
        self.assertEqual(self.stock.quantity, 3)
        self.assertEqual(self.stock.reserved_quantity, 0)

    def test_ajax_cart_rejects_quantity_over_available_stock(self):
        response = self.client.post(
            reverse('add_to_cart'),
            {'product_id': self.product.pk, 'quantity': 6},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['ok'])

    def test_ajax_cart_rejects_add_over_remaining_stock(self):
        self.client.post(reverse('add_to_cart'), {'product_id': self.product.pk, 'quantity': 4})

        response = self.client.post(
            reverse('add_to_cart'),
            {'product_id': self.product.pk, 'quantity': 2},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload['ok'])
        self.assertEqual(payload['cart_quantity'], 4)
        self.assertEqual(payload['remaining_quantity'], 1)

    def test_ajax_cart_update_clamps_quantity_to_available_stock(self):
        self.client.post(reverse('add_to_cart'), {'product_id': self.product.pk, 'quantity': 1})

        response = self.client.post(
            reverse('update_cart'),
            {'product_id': self.product.pk, 'quantity': 9},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['items'][0]['quantity'], 5)
        self.assertIn('доступного остатка', payload['message'])

    def test_checkout_creates_order_and_reserves_stock(self):
        self.client.post(reverse('add_to_cart'), {'product_id': self.product.pk, 'quantity': 2})
        response = self.client.post(
            reverse('checkout'),
            {
                'customer_name': 'Иван',
                'customer_phone': '+79990000000',
                'customer_email': 'ivan@example.com',
                'delivery_address': 'Тюмень',
                'comment': 'Позвонить заранее',
            },
        )

        self.assertEqual(response.status_code, 302)
        order = Order.objects.get()
        self.assertEqual(order.subtotal, self.product.price * 2)
        self.assertTrue(order.stock_reserved)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.reserved_quantity, 2)

    def test_cart_page_clamps_quantity_to_available_stock(self):
        session = self.client.session
        session['doorsky_cart'] = {str(self.product.pk): 9}
        session.save()

        response = self.client.get(reverse('cart'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session['doorsky_cart'][str(self.product.pk)], 5)
        self.assertContains(response, 'уменьшено до доступного остатка')

    def test_payment_simulation_marks_order_paid_and_generates_documents(self):
        self.client.post(reverse('add_to_cart'), {'product_id': self.product.pk, 'quantity': 2})
        checkout_response = self.client.post(
            reverse('checkout'),
            {
                'customer_name': 'Иван',
                'customer_phone': '+79990000000',
                'customer_email': 'ivan@example.com',
                'delivery_address': 'Тюмень',
                'payment_method': Order.PAYMENT_CARD,
            },
        )
        order = Order.objects.get()
        self.assertRedirects(checkout_response, order.get_payment_url(), fetch_redirect_response=False)

        payment_response = self.client.post(
            order.get_payment_url(),
            {
                'scenario': 'success',
                'card_holder': 'IVAN IVANOV',
                'card_number': '4111111111111111',
                'card_expiry': '12/30',
                'card_cvc': '123',
            },
        )

        self.assertRedirects(payment_response, order.get_absolute_url(), fetch_redirect_response=False)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PAYMENT_PAID)
        self.assertEqual(order.status, Order.STATUS_IN_PROGRESS)
        self.assertTrue(order.payment_reference)
        self.assertEqual(PaymentTransaction.objects.filter(order=order, status=PaymentTransaction.STATUS_SUCCEEDED).count(), 1)

        pdf_response = self.client.get(
            reverse(
                'order_public_document_pdf',
                kwargs={'pk': order.pk, 'public_key': order.public_key, 'document_type': 'receipt'},
            )
        )
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response['Content-Type'], 'application/pdf')
        self.assertEqual(pdf_response['X-Frame-Options'], 'SAMEORIGIN')
        self.assertTrue(pdf_response['Content-Disposition'].startswith('inline;'))
        self.assertTrue(pdf_response.content.startswith(b'%PDF'))

        download_response = self.client.get(
            reverse(
                'order_public_document_pdf',
                kwargs={'pk': order.pk, 'public_key': order.public_key, 'document_type': 'receipt'},
            )
            + '?download=1'
        )
        self.assertEqual(download_response.status_code, 200)
        self.assertTrue(download_response['Content-Disposition'].startswith('attachment;'))

        zip_response = self.client.get(
            reverse('order_public_documents_zip', kwargs={'pk': order.pk, 'public_key': order.public_key})
        )
        self.assertEqual(zip_response.status_code, 200)
        with ZipFile(BytesIO(zip_response.content)) as archive:
            names = archive.namelist()
            self.assertIn(f'doorsky-invoice-{order.pk}.pdf', names)
            self.assertIn(f'doorsky-receipt-{order.pk}.pdf', names)
            self.assertFalse(any(name.endswith(('.png', '.docx')) for name in names))

# Create your tests here.
