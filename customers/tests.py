from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, DoorProduct, StockItem
from orders.models import Order

from .models import CustomerProfile, DeliveryAddress


class CustomerAccountTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name='Раздвижные двери', slug='sliding-doors')
        self.product = DoorProduct.objects.create(
            category=category,
            name='Client Slide',
            slug='client-slide',
            sku='DSK-CLIENT-1',
            price=91000,
            opening_type=DoorProduct.OPENING_SLIDING,
        )
        self.stock = StockItem.objects.create(product=self.product, quantity=4, reserved_quantity=0)

    def test_customer_can_register_and_get_profile(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'buyer',
                'full_name': 'Иван Покупатель',
                'email': 'buyer@example.com',
                'phone': '+79990000000',
                'password1': 'StrongPass12345',
                'password2': 'StrongPass12345',
            },
        )

        self.assertRedirects(response, reverse('account_dashboard'))
        user = get_user_model().objects.get(username='buyer')
        self.assertTrue(CustomerProfile.objects.filter(user=user, phone='+79990000000').exists())
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_checkout_prefills_saved_customer_data_and_address(self):
        user = get_user_model().objects.create_user(
            username='saved',
            email='saved@example.com',
            password='StrongPass12345',
        )
        profile = CustomerProfile.objects.create(
            user=user,
            full_name='Мария Клиент',
            phone='+79991112233',
        )
        address = DeliveryAddress.objects.create(
            user=user,
            title='Дом',
            recipient_name='Мария Клиент',
            phone='+79991112233',
            address='Екатеринбург, Ленина 1',
            is_default=True,
        )
        profile.default_address = address
        profile.save(update_fields=['default_address'])
        self.client.force_login(user)
        self.client.post(reverse('add_to_cart'), {'product_id': self.product.pk, 'quantity': 1})

        response = self.client.get(reverse('checkout'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Мария Клиент')
        self.assertContains(response, '+79991112233')
        self.assertContains(response, 'Екатеринбург, Ленина 1')
        self.assertContains(response, 'Сохраненный адрес')

    def test_authenticated_checkout_saves_order_profile_and_delivery_address(self):
        user = get_user_model().objects.create_user(username='checkout', password='StrongPass12345')
        self.client.force_login(user)
        self.client.post(reverse('add_to_cart'), {'product_id': self.product.pk, 'quantity': 2})

        response = self.client.post(
            reverse('checkout'),
            {
                'customer_name': 'Анна Заказчик',
                'customer_phone': '+79001234567',
                'customer_email': 'anna@example.com',
                'delivery_address': 'Тюмень, Республики 10',
                'payment_method': Order.PAYMENT_CASH_ON_DELIVERY,
                'save_delivery_address': 'on',
                'make_default_address': 'on',
            },
        )

        order = Order.objects.get(user=user)
        self.assertRedirects(response, order.get_absolute_url(), fetch_redirect_response=False)
        self.assertEqual(order.customer_name, 'Анна Заказчик')
        self.assertEqual(order.delivery_address, 'Тюмень, Республики 10')

        profile = user.customer_profile
        self.assertEqual(profile.full_name, 'Анна Заказчик')
        self.assertEqual(profile.phone, '+79001234567')
        user.refresh_from_db()
        self.assertEqual(user.email, 'anna@example.com')
        self.assertEqual(user.delivery_addresses.count(), 1)
        address = user.delivery_addresses.get()
        self.assertEqual(address.address, 'Тюмень, Республики 10')
        self.assertTrue(address.is_default)
        self.assertEqual(profile.default_address, address)
        self.assertContains(self.client.get(reverse('account_orders')), 'Заказ')

    def test_customer_cannot_see_foreign_order_in_history(self):
        owner = get_user_model().objects.create_user(username='owner', password='StrongPass12345')
        other = get_user_model().objects.create_user(username='other', password='StrongPass12345')
        Order.objects.create(user=owner, customer_name='Owner', customer_phone='+1', subtotal=100)
        Order.objects.create(user=other, customer_name='Other', customer_phone='+2', subtotal=200)
        self.client.force_login(owner)

        response = self.client.get(reverse('account_orders'))

        self.assertContains(response, '100 руб.')
        self.assertNotContains(response, '200 руб.')
