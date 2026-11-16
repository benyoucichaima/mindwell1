# accounts/services.py
"""
Business logic layer for the accounts application.
Separated from views.py to follow Clean Code principles.
"""

import uuid
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db import models, transaction, OperationalError
from django.db.models import Q, Avg, Count
from django.urls import Resolver404, resolve
from django.utils.http import url_has_allowed_host_and_scheme
from django.core.exceptions import PermissionDenied, ValidationError

from .models import (
    CustomUser, PatientProfile, PsychologueProfile,
    Conversation, Message, Call, ClinicalRecord,
)
from consultations.models import Consultation, DoctorRating, Creneau, PaymentRecord
from consultations.scheduling import (
    active_consultation_overlaps,
    generate_slots,
    overlapping_slots,
    slot_matches_current_schedule,
)
from ai_service.models import MessageAnalysis
from .forms import (
    DoctorRatingForm,
    UserUpdateForm,
    PatientProfileForm,
    PsychologueProfileForm,
)
