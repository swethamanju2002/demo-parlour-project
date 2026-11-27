# Phase 7 — Academy & Training Management (Foundation)

This package adds the Academy domain models without changing booking, billing,
inventory, or the existing user model.

## Included
- Course categories and courses
- Explicit Academy trainer profile linked to the existing `accounts.User`
- Batches with trainer, dates, timings, capacity and lifecycle status
- Enrollments using existing CUSTOMER accounts
- Attendance with one record per enrollment/date
- Course modules and per-student module progress
- Assessments, assessment results and certificate records
- Django admin registration for data inspection

## Apply locally

1. Copy the `academy` folder into the project root:
   `D:\projects\demo_parlour\beauty_salon_demo\academy`

2. Add `"academy.apps.AcademyConfig",` to `INSTALLED_APPS` in
   `config/settings.py` (do not replace the file).

3. Run:
   ```powershell
   python manage.py check
   python manage.py makemigrations academy
   python manage.py migrate
   python manage.py check
   ```

4. Verify the migration and tables before continuing:
   ```powershell
   python manage.py showmigrations academy
   python manage.py shell -c "from academy.models import Course, Batch, Enrollment; print('Academy models loaded')"
   ```

## Important design notes
- `AcademyTrainer` is separate from salon `StaffProfile`. The existing StaffProfile
  represents beautician/service capability and is not assumed to be an academy trainer.
- Students are existing `accounts.User` records whose role is `customer`.
- Academy fees are stored as agreed enrollment fees only. This package does not
  connect to or modify the existing salon billing workflow.
- Capacity is validated at model validation level. Enrollment creation in the
  admin workflow must also use a transaction and re-check capacity to prevent
  concurrent over-enrollment; that is part of the next implementation step.
- Certificate eligibility is intentionally not auto-issued here. A policy must be
  enforced in the application service before issuing a certificate.
- No existing migration, database, URL, or template has been changed.
