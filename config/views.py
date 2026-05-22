from urllib.parse import urlencode

from django.conf import settings
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme


def csrf_failure(request, reason=''):
    if request.path == reverse('login'):
        params = {'csrf': '1'}
        next_url = request.POST.get('next') or request.GET.get('next')
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            params['next'] = next_url
        response = redirect(f'{reverse("login")}?{urlencode(params)}')
    else:
        response = render(
            request,
            'csrf_failure.html',
            {'reason': reason},
            status=403,
        )
    response.delete_cookie(
        settings.CSRF_COOKIE_NAME,
        path='/',
        domain=settings.CSRF_COOKIE_DOMAIN,
        samesite=settings.CSRF_COOKIE_SAMESITE,
    )
    return response
