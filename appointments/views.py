from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

@login_required
def book_appointment(request):
    if request.user.user_type != 'patient':
        return redirect('home')
    return redirect('accounts:trouver_psychologue')


@login_required
def patient_dashboard(request):
    from accounts.views import patient_dashboard as accounts_patient_dashboard
    return accounts_patient_dashboard(request)


@login_required
def specialist_dashboard(request):
    from accounts.views import psychologue_dashboard as accounts_psychologue_dashboard
    return accounts_psychologue_dashboard(request)


@login_required
def accept_appointment(request, appointment_id):
    from accounts.views import confirm_appointment
    return confirm_appointment(request, appointment_id)


@login_required
def reject_appointment(request, appointment_id):
    from accounts.views import reject_appointment as accounts_reject_appointment
    return accounts_reject_appointment(request, appointment_id)


@login_required
def cancel_appointment(request, appointment_id):
    from accounts.views import cancel_patient_appointment
    return cancel_patient_appointment(request, appointment_id)


@login_required
def payment_page(request, appointment_id):
    from accounts.views import payment_page as accounts_payment_page
    return accounts_payment_page(request, appointment_id)


@login_required
def process_payment(request, appointment_id):
    from accounts.views import process_payment as accounts_process_payment
    return accounts_process_payment(request, appointment_id)


@login_required
def payment_success(request, appointment_id):
    from accounts.views import payment_success as accounts_payment_success
    return accounts_payment_success(request, appointment_id)


@login_required
def payment_failed(request):
    messages.error(request, 'Le paiement n’a pas pu être effectué.')
    return redirect('accounts:patient_dashboard')