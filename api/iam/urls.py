from django.urls import path

from iam import views

urlpatterns = [
    path("login/", views.login_view, name="auth-login"),
    path("logout/", views.logout_view, name="auth-logout"),
    path("me/", views.me_view, name="auth-me"),
    path("mfa/enrol/", views.mfa_enrol, name="auth-mfa-enrol"),
    path("mfa/verify/", views.mfa_verify, name="auth-mfa-verify"),
]
