from django.shortcuts import render

from accounts.permissions import customer_required


@customer_required
def dashboard(request):
    return render(request, "client/dashboard.html")
