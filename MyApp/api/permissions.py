from rest_framework.permissions import BasePermission

from MyApp.models import login


class ApiAuthenticated(BasePermission):
    message = 'Authentication is required.'

    def has_permission(self, request, view):
        return isinstance(request.user, login)
