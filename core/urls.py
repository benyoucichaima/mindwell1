from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('psychologues/', views.psychologists, name='psychologists'),
    path('faq/', views.faq, name='faq'),
    path('aide/', views.help_center, name='help'),
    path('a-propos/', views.about, name='about'),
    path('carrieres/', views.careers, name='careers'),
    path('blog/', views.blog, name='blog'),
    path('presse/', views.press, name='press'),
    path('urgences/', views.emergency, name='emergency'),
    path('contact/', views.contact, name='contact'),
    path('confidentialite/', views.privacy, name='privacy'),
    path('cgu/', views.terms, name='terms'),
    path('mentions-legales/', views.legal, name='legal'),
    path('cookies/', views.cookies, name='cookies'),
]