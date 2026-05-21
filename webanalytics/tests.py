import json

from django.test import TestCase
from django.urls import reverse

from .models import WebPageView, WebVisit
from .utils import VISITOR_COOKIE


class WebAnalyticsTests(TestCase):
    def test_public_page_view_tracks_device_geo_and_source(self):
        response = self.client.get(
            '/?utm_source=direct-test&utm_medium=cpc&utm_campaign=doors',
            HTTP_USER_AGENT=(
                'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
                'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
            ),
            HTTP_CF_IPCOUNTRY='RU',
            HTTP_X_VERCEL_IP_CITY='Moscow',
            HTTP_REFERER='https://yandex.ru/search/?text=doors',
            REMOTE_ADDR='8.8.8.8',
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(VISITOR_COOKIE, response.cookies)
        visit = WebVisit.objects.get()
        page_view = WebPageView.objects.get()
        self.assertEqual(visit.device_type, WebVisit.DEVICE_MOBILE)
        self.assertEqual(visit.device, 'iPhone')
        self.assertEqual(visit.browser, 'Safari')
        self.assertEqual(visit.os, 'iOS')
        self.assertEqual(visit.country, 'Россия')
        self.assertEqual(visit.city, 'Moscow')
        self.assertEqual(visit.traffic_channel, WebVisit.CHANNEL_PAID)
        self.assertEqual(visit.utm_source, 'direct-test')
        self.assertEqual(page_view.path, '/')

    def test_client_metrics_updates_latest_page_view(self):
        response = self.client.get('/')
        self.assertIn(VISITOR_COOKIE, response.cookies)

        response = self.client.post(
            reverse('webanalytics_client_metrics'),
            data=json.dumps(
                {
                    'path': '/',
                    'viewport_width': 390,
                    'viewport_height': 844,
                    'screen_width': 390,
                    'screen_height': 844,
                    'device_pixel_ratio': 3,
                    'language': 'ru-RU',
                    'timezone': 'Asia/Yekaterinburg',
                    'color_scheme': 'dark',
                    'connection_type': '4g',
                    'engagement_seconds': 12,
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        page_view = WebPageView.objects.get()
        self.assertEqual(page_view.viewport_width, 390)
        self.assertEqual(page_view.viewport_height, 844)
        self.assertEqual(page_view.language, 'ru-RU')
        self.assertEqual(page_view.timezone, 'Asia/Yekaterinburg')
        self.assertEqual(page_view.engagement_seconds, 12)

    def test_backoffice_pages_are_not_tracked(self):
        self.client.get('/office/')

        self.assertEqual(WebVisit.objects.count(), 0)
        self.assertEqual(WebPageView.objects.count(), 0)
