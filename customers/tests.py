import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, DoorProduct, StockItem
from orders.models import Order

from .models import CustomerEmailVerification, CustomerProfile, DeliveryAddress


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    CUSTOMER_EMAIL_CODE_RESEND_COOLDOWN_SECONDS=0,
)
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

        self.assertRedirects(response, reverse('account_email_verify'))
        user = get_user_model().objects.get(username='buyer')
        self.assertTrue(CustomerProfile.objects.filter(user=user, phone='+79990000000').exists())
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)
        self.assertEqual(CustomerEmailVerification.objects.filter(user=user, email='buyer@example.com').count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', EMAIL_HOST='')
    def test_registration_shows_verification_code_when_email_is_not_configured(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'no-mail',
                'full_name': 'Нет Почты',
                'email': 'no-mail@example.com',
                'phone': '+79990000999',
                'password1': 'StrongPass12345',
                'password2': 'StrongPass12345',
            },
            follow=True,
        )

        self.assertContains(response, 'Почтовый клиент не настроен. Код подтверждения:')
        self.assertRegex(response.content.decode(), r'Код подтверждения: \d{6}')
        user = get_user_model().objects.get(username='no-mail')
        self.assertEqual(CustomerEmailVerification.objects.filter(user=user, email='no-mail@example.com').count(), 1)

    def test_customer_can_login_with_email(self):
        get_user_model().objects.create_user(
            username='email-login',
            email='login@example.com',
            password='StrongPass12345',
        )

        response = self.client.post(
            reverse('login'),
            {
                'username': 'login@example.com',
                'password': 'StrongPass12345',
            },
        )

        self.assertRedirects(response, reverse('catalog'))

    def test_login_csrf_failure_refreshes_form(self):
        csrf_client = Client(enforce_csrf_checks=True)

        response = csrf_client.post(
            f'{reverse("login")}?next=/office/',
            {
                'username': 'buyer',
                'password': 'wrong-pass',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(f'{reverse("login")}?csrf=1', response['Location'])
        self.assertIn('next=%2Foffice%2F', response['Location'])

    def test_customer_can_verify_email_with_code(self):
        self.client.post(
            reverse('register'),
            {
                'username': 'verify',
                'full_name': 'Вера Клиент',
                'email': 'verify@example.com',
                'phone': '+79990000001',
                'password1': 'StrongPass12345',
                'password2': 'StrongPass12345',
            },
        )
        code = re.search(r'\b\d{6}\b', mail.outbox[-1].body).group(0)

        response = self.client.post(reverse('account_email_verify'), {'code': code})

        self.assertRedirects(response, reverse('account_dashboard'))
        user = get_user_model().objects.get(username='verify')
        self.assertTrue(user.customer_profile.is_email_verified)
        self.assertTrue(user.email_verification_codes.filter(verified_at__isnull=False).exists())

    def test_invalid_email_code_increments_attempts(self):
        self.client.post(
            reverse('register'),
            {
                'username': 'wrong-code',
                'full_name': 'Код Ошибка',
                'email': 'wrong-code@example.com',
                'phone': '+79990000002',
                'password1': 'StrongPass12345',
                'password2': 'StrongPass12345',
            },
        )
        verification = CustomerEmailVerification.objects.get(email='wrong-code@example.com')

        response = self.client.post(reverse('account_email_verify'), {'code': '000000'})

        self.assertEqual(response.status_code, 200)
        verification.refresh_from_db()
        self.assertEqual(verification.attempts, 1)
        self.assertFalse(verification.verified_at)

    def test_profile_email_change_resets_verification_and_sends_code(self):
        user = get_user_model().objects.create_user(
            username='profile-email',
            email='old@example.com',
            password='StrongPass12345',
        )
        CustomerProfile.objects.create(user=user, full_name='Old Name', email_verified_at=timezone.now())
        self.client.force_login(user)

        response = self.client.post(
            reverse('account_profile'),
            {
                'full_name': 'New Name',
                'email': 'new@example.com',
                'phone': '+79995554433',
                'customer_type': CustomerProfile.CUSTOMER_INDIVIDUAL,
            },
        )

        self.assertRedirects(response, reverse('account_email_verify'))
        user.refresh_from_db()
        self.assertEqual(user.email, 'new@example.com')
        self.assertIsNone(user.customer_profile.email_verified_at)
        self.assertEqual(CustomerEmailVerification.objects.filter(user=user, email='new@example.com').count(), 1)
        self.assertEqual(len(mail.outbox), 1)

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
        orders_response = self.client.get(reverse('account_orders'))
        self.assertContains(orders_response, 'Заказ')
        self.assertContains(orders_response, 'Чек PDF')
        self.assertContains(orders_response, 'Накладная PDF')

        dashboard_response = self.client.get(reverse('account_dashboard'))
        self.assertContains(dashboard_response, 'История и документы')
        self.assertContains(dashboard_response, 'ZIP')

    def test_customer_cannot_see_foreign_order_in_history(self):
        owner = get_user_model().objects.create_user(username='owner', password='StrongPass12345')
        other = get_user_model().objects.create_user(username='other', password='StrongPass12345')
        Order.objects.create(user=owner, customer_name='Owner', customer_phone='+1', subtotal=100)
        Order.objects.create(user=other, customer_name='Other', customer_phone='+2', subtotal=200)
        self.client.force_login(owner)

        response = self.client.get(reverse('account_orders'))

        self.assertContains(response, '100 руб.')
        self.assertNotContains(response, '200 руб.')
