from django.shortcuts import render

from accounts.permissions import salon_team_required


@salon_team_required
def dashboard(request):
    return render(request, "admin_panel/dashboard.html")
