from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="auth-login"),
    path("login/mfa/", views.MFALoginView.as_view(), name="auth-login-mfa"),
    path("refresh/", views.RefreshView.as_view(), name="auth-refresh"),
    path("logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("me/", views.MeView.as_view(), name="auth-me"),
    path("password/reset/", views.PasswordResetRequestView.as_view(), name="password-reset"),
    path(
        "password/reset/confirm/",
        views.PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path("password/change/", views.PasswordChangeView.as_view(), name="password-change"),
    path("mfa/", views.MFAStatusView.as_view(), name="mfa-status"),
    path("mfa/setup/", views.MFASetupView.as_view(), name="mfa-setup"),
    path("mfa/enable/", views.MFAEnableView.as_view(), name="mfa-enable"),
    path("mfa/disable/", views.MFADisableView.as_view(), name="mfa-disable"),
    path("mfa/recovery-codes/", views.MFARecoveryCodesView.as_view(), name="mfa-recovery-codes"),
]
