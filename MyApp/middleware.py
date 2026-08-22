from functools import wraps
import re
import time

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .models import login


PUBLIC_WMS_PATHS = frozenset(('/WMS/login/', '/WMS/login_post/'))
ROLE_EQUIVALENTS = {
    'Project Engineer': frozenset(('Project Manager',)),
    'Operation Manager': frozenset(('Admin', 'Project Manager')),
}


def role_is_allowed(actual_role, allowed_roles):
    return actual_role in allowed_roles or bool(
        ROLE_EQUIVALENTS.get(actual_role, frozenset()).intersection(allowed_roles)
    )


class LegacySessionAuthenticationMiddleware:
    """Require the legacy application session for every non-public WMS route."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        is_mobile_api = request.path.startswith('/WMS/api/')
        if request.path.startswith('/WMS/') and request.path not in PUBLIC_WMS_PATHS and not is_mobile_api:
            login_id = request.session.get('lid')
            if not login_id:
                return redirect('login')
            account = login.objects.filter(pk=login_id).only(
                'usertype', 'api_token_version',
            ).first()
            if not account:
                request.session.flush()
                return redirect('login')
            session_version = request.session.get('auth_version')
            if session_version is None:
                # Mark pre-versioned sessions on first use for compatibility.
                request.session['auth_version'] = account.api_token_version
            else:
                try:
                    version_matches = int(session_version) == account.api_token_version
                except (TypeError, ValueError):
                    version_matches = False
                if not version_matches:
                    request.session.flush()
                    return redirect('login')
            last_activity = request.session.get('last_activity')
            try:
                idle_seconds = time.time() - float(last_activity) if last_activity else 0
            except (TypeError, ValueError):
                idle_seconds = settings.WMS_SESSION_IDLE_TIMEOUT + 1
            if idle_seconds > settings.WMS_SESSION_IDLE_TIMEOUT:
                request.session.flush()
                return redirect('login')
            request.session['last_activity'] = timezone.now().timestamp()
            if not request.session.get('role'):
                request.session['role'] = account.usertype
        return self.get_response(request)


def legacy_role_required(*roles):
    """Authorize legacy function views using the role stored at login."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not role_is_allowed(request.session.get('role'), roles):
                return HttpResponseForbidden('You do not have permission to perform this action.')
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


class LegacyScriptAlertMiddleware:
    """Convert legacy blank JavaScript alert pages into normal redirects and banners."""

    alert_pattern = re.compile(r"alert\(['\"](?P<message>.*?)['\"]\)", re.DOTALL)
    location_pattern = re.compile(r"window\.location\s*=\s*['\"](?P<url>[^'\"]+)['\"]")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        content_type = response.get('Content-Type', '')
        if response.streaming or 'text/html' not in content_type:
            return response
        try:
            body = response.content.decode(response.charset or 'utf-8')
        except (AttributeError, UnicodeDecodeError):
            return response
        if '<script' not in body or 'alert(' not in body:
            return response
        alert_match = self.alert_pattern.search(body)
        if not alert_match:
            return response
        location_match = self.location_pattern.search(body)
        target = location_match.group('url') if location_match else request.META.get('HTTP_REFERER', '')
        if not target or not url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            target = request.META.get('HTTP_REFERER') or '/WMS/'
        message = alert_match.group('message').replace('\\\'', "'").strip()
        error_words = ('invalid', 'error', 'mismatch', 'must', 'failed', 'already exists', 'required')
        if response.status_code >= 400 or any(word in message.lower() for word in error_words):
            messages.error(request, message)
        else:
            messages.success(request, message)
        return redirect(target)
