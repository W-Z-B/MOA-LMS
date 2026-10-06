from django.urls import path

from iam import account_views, email_views, review, views

urlpatterns = [
    path("login/", views.login_view, name="auth-login"),
    path("logout/", views.logout_view, name="auth-logout"),
    path("me/", views.me_view, name="auth-me"),
    path("mfa/enrol/", views.mfa_enrol, name="auth-mfa-enrol"),
    path("mfa/verify/", views.mfa_verify, name="auth-mfa-verify"),
    path("sessions/", views.sessions_view, name="auth-sessions"),
    path("sessions/end-others/", views.end_other_sessions_view, name="auth-sessions-end-others"),
    path("sessions/<int:pk>/", views.end_session_view, name="auth-session-end"),
    path("access-review/", review.access_review_view, name="auth-access-review"),
    path("access-review/sign-off/", review.access_review_sign_off, name="auth-access-review-sign-off"),
    path("password/forgot/", views.forgot_password_view, name="auth-password-forgot"),
    path("password/check/", views.check_link_view, name="auth-password-check"),
    path("password/set/", views.set_password_view, name="auth-password-set"),
    path("password/change/", views.change_password_view, name="auth-password-change"),
    path("email/", email_views.email_view, name="auth-email"),
    path("email/change/", email_views.change_email_view, name="auth-email-change"),
    path("email/confirm/", email_views.confirm_email_view, name="auth-email-confirm"),
    path("accounts/uninvited/", account_views.uninvited_view, name="auth-accounts-uninvited"),
    path("accounts/invite/", account_views.invite_all_view, name="auth-accounts-invite"),
    path("accounts/invite/<int:person_id>/", account_views.invite_one_view, name="auth-accounts-invite-one"),
]
