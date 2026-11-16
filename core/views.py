from django.shortcuts import render
from django.db.models import Avg, Count
from accounts.models import PsychologueProfile

def home(request):
    featured_psychologists = PsychologueProfile.objects.filter(
        is_verified=True,
        user__is_active=True,
    ).select_related('user').annotate(
        rating_average=Avg('user__ratings_received__rating'),
        rating_count=Count('user__ratings_received', distinct=True),
    ).order_by('-rating_count', 'user__last_name')[:3]
    return render(
        request,
        'pages/home.html',
        {'featured_psychologists': featured_psychologists},
    )

def psychologists(request):
    psychologists = PsychologueProfile.objects.filter(
        is_verified=True,
        user__is_active=True,
    ).select_related('user').annotate(
        rating_average=Avg('user__ratings_received__rating'),
        rating_count=Count('user__ratings_received', distinct=True),
    ).order_by('-rating_count', 'user__last_name')
    return render(
        request,
        'pages/psychologists.html',
        {'psychologists': psychologists},
    )

def faq(request):
    from mindwell.views import faq as faq_view

    return faq_view(request)

def help_center(request):
    from mindwell.views import aide

    return aide(request)

def about(request):
    return render(request, 'pages/about.html')

def careers(request):
    return render(request, 'pages/carriere.html')

def blog(request):
    return render(request, 'pages/blog.html')

def press(request):
    return render(request, 'pages/press.html')

def emergency(request):
    return render(request, 'pages/urgence.html')

def contact(request):
    from mindwell.views import contact as contact_view

    return contact_view(request)

def privacy(request):
    return render(request, 'pages/privacy.html')

def terms(request):
    return render(request, 'pages/cgv.html')

def legal(request):
    return render(request, 'pages/legal.html')

def cookies(request):
    return render(request, 'pages/cookies.html')