import uuid
from datetime import timedelta

from django.utils import timezone

from .models import WebPageView, WebVisit
from .utils import (
    VISIT_TIMEOUT_MINUTES,
    VISITOR_COOKIE,
    get_client_ip,
    get_geo,
    get_utm,
    parse_referrer,
    parse_user_agent,
    should_track_path,
    traffic_channel_from_utm,
)


class WebAnalyticsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            self._track(request, response)
        except Exception:
            return response
        return response

    def _track(self, request, response):
        if request.method != 'GET':
            return
        if not should_track_path(request.path):
            return
        if response.status_code >= 500:
            return
        content_type = response.get('Content-Type', '')
        if 'text/html' not in content_type:
            return

        visitor_id = request.COOKIES.get(VISITOR_COOKIE) or str(uuid.uuid4())
        now = timezone.now()
        timeout_at = now - timedelta(minutes=VISIT_TIMEOUT_MINUTES)
        user = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None
        full_path = request.get_full_path()[:1000]

        visit = (
            WebVisit.objects.filter(visitor_id=visitor_id, last_seen_at__gte=timeout_at)
            .order_by('-last_seen_at')
            .first()
        )
        if visit is None:
            referrer, referrer_domain, fallback_channel = parse_referrer(request)
            utm = get_utm(request)
            visit = WebVisit.objects.create(
                visitor_id=visitor_id,
                session_key=getattr(request.session, 'session_key', '') or '',
                user=user,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:1000],
                referrer=referrer,
                referrer_domain=referrer_domain,
                traffic_channel=traffic_channel_from_utm(utm, fallback_channel),
                landing_path=full_path,
                exit_path=full_path,
                last_seen_at=now,
                **parse_user_agent(request.META.get('HTTP_USER_AGENT', '')),
                **get_geo(request),
                **utm,
            )

        visit.user = visit.user or user
        visit.page_views_count += 1
        visit.exit_path = full_path
        visit.last_seen_at = now
        visit.save(update_fields=['user', 'page_views_count', 'exit_path', 'last_seen_at'])

        WebPageView.objects.create(
            visit=visit,
            user=user,
            path=request.path[:600],
            full_path=full_path,
            referrer=(request.META.get('HTTP_REFERER') or '')[:800],
            status_code=response.status_code,
        )
        response.set_cookie(
            VISITOR_COOKIE,
            visitor_id,
            max_age=60 * 60 * 24 * 400,
            samesite='Lax',
            secure=request.is_secure(),
        )
