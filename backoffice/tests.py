from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, DoorProduct, StockItem, StockMovement
from customers.models import EmailClientSettings


class BackofficeTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username='manager',
            password='manager-pass',
            is_staff=True,
        )
        self.superuser = get_user_model().objects.create_superuser(
            username='owner',
            password='owner-pass',
        )
        self.staff.user_permissions.add(
            Permission.objects.get(codename='view_doorproduct', content_type__app_label='catalog'),
            Permission.objects.get(codename='add_doorproduct', content_type__app_label='catalog'),
            Permission.objects.get(codename='change_doorproduct', content_type__app_label='catalog'),
            Permission.objects.get(codename='change_stockitem', content_type__app_label='catalog'),
            Permission.objects.get(codename='view_stockitem', content_type__app_label='catalog'),
        )
        self.category = Category.objects.create(name='Раздвижные', slug='sliding')
        self.product = DoorProduct.objects.create(
            category=self.category,
            name='Slide Pro',
            slug='slide-pro',
            sku='DSK-BO-1',
            price=120000,
            opening_type=DoorProduct.OPENING_SLIDING,
        )
        self.stock = StockItem.objects.create(product=self.product, quantity=5, reserved_quantity=1, min_quantity=1)

    def test_backoffice_requires_staff_login_and_admin_redirects(self):
        response = self.client.get(reverse('backoffice_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])

        self.client.force_login(self.staff)
        response = self.client.get('/admin/')
        self.assertRedirects(response, reverse('backoffice_dashboard'), fetch_redirect_response=False)

    def test_staff_can_update_stock_from_catalog(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse('backoffice_catalog'),
            {
                'action': 'stock_update',
                'product_id': self.product.pk,
                'quantity': 9,
                'reserved_quantity': 2,
                'min_quantity': 3,
            },
        )

        self.assertRedirects(response, reverse('backoffice_catalog'), fetch_redirect_response=False)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 9)
        self.assertEqual(self.stock.reserved_quantity, 2)
        self.assertEqual(self.stock.min_quantity, 3)
        self.assertTrue(
            StockMovement.objects.filter(
                product=self.product,
                movement_type=StockMovement.TYPE_ADJUSTMENT,
                quantity=4,
            ).exists()
        )

    def test_staff_can_create_product_with_stock(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse('backoffice_product_create'),
            {
                'category': self.category.pk,
                'name': 'Pocket Deluxe',
                'slug': '',
                'sku': 'DSK-BO-2',
                'description': 'Новая позиция из панели.',
                'price': '145000',
                'width_min_mm': 700,
                'width_max_mm': 1200,
                'height_min_mm': 2000,
                'height_max_mm': 3000,
                'material': 'Алюминий',
                'color': 'Графит',
                'finish': 'Стекло',
                'opening_type': DoorProduct.OPENING_SLIDING,
                'image_url': '',
                'source_url': '',
                'is_active': 'on',
                'quantity': 7,
                'reserved_quantity': 0,
                'min_quantity': 2,
            },
        )

        product = DoorProduct.objects.get(sku='DSK-BO-2')
        self.assertRedirects(response, reverse('backoffice_product_edit', kwargs={'pk': product.pk}))
        self.assertEqual(product.name, 'Pocket Deluxe')
        self.assertEqual(product.stock.quantity, 7)
        self.assertEqual(product.stock.min_quantity, 2)

    def test_staff_can_open_analytics_with_stock_permission(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse('backoffice_analytics'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Аналитика')
        self.assertContains(response, 'Доступно на складе')

    def test_superuser_can_create_staff_user_and_assign_role(self):
        self.client.force_login(self.superuser)
        self.client.get(reverse('backoffice_users'))
        group = Group.objects.get(name='DoorSky: менеджер заказов')

        response = self.client.post(
            reverse('backoffice_user_create'),
            {
                'username': 'sales-manager',
                'first_name': 'Sales',
                'last_name': 'Manager',
                'email': 'sales@example.com',
                'password1': 'strong-manager-pass-123',
                'password2': 'strong-manager-pass-123',
                'is_active': 'on',
                'is_staff': 'on',
                'groups': [str(group.pk)],
            },
        )

        user = get_user_model().objects.get(username='sales-manager')
        self.assertRedirects(response, reverse('backoffice_user_edit', kwargs={'pk': user.pk}))
        self.assertTrue(user.is_staff)
        self.assertTrue(user.groups.filter(pk=group.pk).exists())
        self.assertTrue(user.has_perm('orders.view_order'))

    def test_superuser_can_update_email_settings_without_exposing_password(self):
        self.client.force_login(self.superuser)

        response = self.client.post(
            reverse('backoffice_email_settings'),
            {
                'is_enabled': 'on',
                'host': 'smtp.example.com',
                'port': 587,
                'username': 'doorsky-mailer',
                'password': 'smtp-secret-value',
                'from_email': 'DoorSky <noreply@example.com>',
                'use_tls': 'on',
                'timeout_seconds': 12,
                'action': 'save',
            },
        )

        self.assertRedirects(response, reverse('backoffice_email_settings'))
        email_settings = EmailClientSettings.objects.get(pk=1)
        self.assertTrue(email_settings.is_enabled)
        self.assertEqual(email_settings.host, 'smtp.example.com')
        self.assertEqual(email_settings.get_password(), 'smtp-secret-value')
        self.assertNotEqual(email_settings.encrypted_password, 'smtp-secret-value')

        response = self.client.get(reverse('backoffice_email_settings'))
        self.assertContains(response, 'smtp.example.com')
        self.assertContains(response, 'Сохранен')
        self.assertNotContains(response, 'smtp-secret-value')

    def test_staff_cannot_open_email_settings(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse('backoffice_email_settings'))

        self.assertEqual(response.status_code, 403)
