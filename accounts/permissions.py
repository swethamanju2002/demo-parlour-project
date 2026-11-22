from functools import wraps

from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied


def _check(request, predicate):
    if not request.user.is_authenticated:
        return None
    return predicate(request.user)


def customer_required(view):
    @wraps(view)
    def wrapper(request, *a, **kw):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if request.user.role != "customer":
            raise PermissionDenied
        return view(request, *a, **kw)
    return wrapper


def salon_team_required(view):
    @wraps(view)
    def wrapper(request, *a, **kw):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if not request.user.is_salon_team:
            raise PermissionDenied
        return view(request, *a, **kw)
    return wrapper


def salon_admin_required(view):
    @wraps(view)
    def wrapper(request, *a, **kw):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if not request.user.is_salon_admin:
            raise PermissionDenied
        return view(request, *a, **kw)
    return wrapper


class CustomerRequiredMixin(AccessMixin):
    def dispatch(self, request, *a, **kw):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.role != "customer":
            raise PermissionDenied
        return super().dispatch(request, *a, **kw)


class SalonTeamRequiredMixin(AccessMixin):
    def dispatch(self, request, *a, **kw):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_salon_team:
            raise PermissionDenied
        return super().dispatch(request, *a, **kw)
