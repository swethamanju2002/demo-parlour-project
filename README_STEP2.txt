DQ AESTHETIC — PHASE 7 / STEP 2
Academy admin dashboard + CRUD for categories, courses, trainers and batches.

COPY:
- academy/forms.py
- academy/admin_views.py
- academy/admin_urls.py
- academy/tests/test_admin_views.py
- templates/admin_panel/academy/ (all templates)
- static/css/admin/academy.css

INTEGRATION A — URLS:
Open bookings/admin_urls.py. At the very bottom, after the existing inventory URL extension, append:

from academy.admin_urls import urlpatterns as academy_urlpatterns
urlpatterns += academy_urlpatterns

Do not replace the existing urlpatterns or remove inventory routes.

INTEGRATION B — ADMIN NAV:
Open templates/base/public.html. In the admin-navigation section, add this link near Billing/Inventory:

<a href="{% url 'admin_panel:academy_dashboard' %}"
   class="admin-nav-link {% if 'academy' in request.resolver_match.url_name %}active{% endif %}">
    Academy
</a>

INTEGRATION C — OPTIONAL DASHBOARD CARD:
In templates/admin_panel/dashboard.html, inside management-grid, add:

<a href="{% url 'admin_panel:academy_dashboard' %}" class="management-card">
  <span class="management-number">08</span>
  <div class="management-icon">✧</div>
  <h3>Academy & Training</h3>
  <p>Manage courses, trainers, batches and student training programmes.</p>
  <span class="management-link">Manage academy →</span>
</a>

RUN:
python manage.py check
python manage.py test academy
python manage.py test

SMOKE TEST:
1. Log in with a role=admin account.
2. Open /admin-panel/academy/
3. Create a category.
4. Create a course under that category.
5. Ensure an existing User with role=staff or role=admin is active, then add as Academy Trainer.
6. Create a batch using the course and trainer.
7. Edit each record and toggle active states.
8. Log in as a customer and verify /admin-panel/academy/ returns 403.
9. Verify existing /admin-panel/billing/ and /admin-panel/inventory/ still load.

NOTES:
- All mutations use POST + CSRF for active/inactive and batch status changes.
- All Academy admin pages are protected by salon_admin_required.
- This step implements CRUD for category/course/trainer/batch. Student admissions, attendance, learning progress, assessments, certificates, reports and trainer permissions remain subsequent steps.
- The batch status button advances PLANNED -> ENROLLING -> ONGOING -> COMPLETED. There is no cancel action in this basic UI; cancellation can be added with the dedicated workflow step.
- The package does not alter billing or connect Academy fees to salon invoices.
