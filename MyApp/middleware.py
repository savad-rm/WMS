from functools import wraps

from django.http import HttpResponseForbidden
from django.shortcuts import redirect

from .models import login


PUBLIC_WMS_PATHS = frozenset(('/WMS/login/', '/WMS/login_post/'))


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
            if not request.session.get('role'):
                role = login.objects.filter(pk=login_id).values_list('usertype', flat=True).first()
                if not role:
                    request.session.flush()
                    return redirect('login')
                request.session['role'] = role
        return self.get_response(request)


def legacy_role_required(*roles):
    """Authorize legacy function views using the role stored at login."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.session.get('role') not in roles:
                return HttpResponseForbidden('You do not have permission to perform this action.')
            return view(request, *args, **kwargs)
        return wrapped
    return decorator
