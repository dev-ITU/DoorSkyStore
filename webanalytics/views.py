import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import WebPageView
from .utils import VISITOR_COOKIE, should_track_path


def _positive_int(value, maximum):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    if value < 0:
        return None
    return min(value, maximum)


def _decimal(value, maximum):
    try:
        value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if value < 0:
        return None
    return min(value, Decimal(str(maximum)))


def _clean(value, max_length):
    if not value:
        return ''
    return str(value).strip()[:max_length]


@csrf_exempt
@require_POST
def client_metrics(request):
    visitor_id = request.COOKIES.get(VISITOR_COOKIE)
    if not visitor_id:
        return JsonResponse({'ok': True})
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'ok': False}, status=400)

    path = _clean(payload.get('path'), 600)
    if not should_track_path(path):
        return JsonResponse({'ok': True})

    page_view = (
        WebPageView.objects.filter(
            visit__visitor_id=visitor_id,
            path=path,
            created_at__gte=timezone.now() - timedelta(minutes=10),
        )
        .order_by('-created_at')
        .first()
    )
    if not page_view:
        return JsonResponse({'ok': True})

    page_view.viewport_width = _positive_int(payload.get('viewport_width'), 10000)
    page_view.viewport_height = _positive_int(payload.get('viewport_height'), 10000)
    page_view.screen_width = _positive_int(payload.get('screen_width'), 10000)
    page_view.screen_height = _positive_int(payload.get('screen_height'), 10000)
    page_view.device_pixel_ratio = _decimal(payload.get('device_pixel_ratio'), 10)
    page_view.language = _clean(payload.get('language'), 40)
    page_view.timezone = _clean(payload.get('timezone'), 80)
    page_view.color_scheme = _clean(payload.get('color_scheme'), 20)
    page_view.connection_type = _clean(payload.get('connection_type'), 40)
    engagement_seconds = _positive_int(payload.get('engagement_seconds'), 60 * 60 * 12)
    if engagement_seconds is not None:
        page_view.engagement_seconds = max(page_view.engagement_seconds, engagement_seconds)
    page_view.save(
        update_fields=[
            'viewport_width',
            'viewport_height',
            'screen_width',
            'screen_height',
            'device_pixel_ratio',
            'language',
            'timezone',
            'color_scheme',
            'connection_type',
            'engagement_seconds',
        ]
    )
    return JsonResponse({'ok': True})
