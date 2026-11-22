from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render

from .forms import LoginForm, ProfileForm, RegisterForm


class SalonLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


@login_required
def post_login(request):
    """Send each role to its own home after sign-in."""
    if request.user.is_salon_team:
        return redirect("admin_panel:dashboard")
    return redirect("client:dashboard")


def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:post_login")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, f"Welcome to DQ Aesthetic, {user.first_name}. Your account is ready.")
        return redirect("client:dashboard")
    return render(request, "accounts/register.html", {"form": form})


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile saved.")
        return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"form": form})
