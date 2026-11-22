import time

import pyotp
import pytest
from django.urls import reverse

from apps.accounts import mfa
from apps.accounts.models import SecurityEvent, User
from conftest import PASSWORD, client_for

pytestmark = pytest.mark.django_db


def current_code(user: User) -> str:
    user.refresh_from_db()
    return pyotp.TOTP(mfa._decrypt(user)).now()


def next_code(user: User) -> str:
    """Código del siguiente intervalo (válido por la tolerancia ±1 y distinto del actual)."""
    user.refresh_from_db()
    return pyotp.TOTP(mfa._decrypt(user)).at(int(time.time()) + 30)


@pytest.fixture
def mfa_user(user) -> tuple[User, list[str]]:
    mfa.start_setup(user)
    codes = mfa.enable(user)
    return user, codes


class TestSetup:
    def test_setup_and_enable(self, auth_api, user):
        setup = auth_api.post(reverse("mfa-setup")).json()
        assert setup["otpauth_uri"].startswith("otpauth://totp/")
        assert "<svg" in setup["qr_svg"]
        user.refresh_from_db()
        assert setup["secret"] not in user.mfa_secret  # cifrado en reposo

        bad = auth_api.post(reverse("mfa-enable"), {"code": "000000"}, format="json")
        assert bad.status_code == 400
        ok = auth_api.post(reverse("mfa-enable"), {"code": current_code(user)}, format="json")
        assert ok.status_code == 200
        assert len(ok.json()["recovery_codes"]) == 10
        assert auth_api.get(reverse("mfa-status")).json() == {
            "enabled": True,
            "recovery_codes_remaining": 10,
        }

    def test_code_cannot_be_reused(self, mfa_user):
        user, _ = mfa_user
        code = current_code(user)
        assert mfa.verify_totp(user, code)
        assert not mfa.verify_totp(user, code)


class TestLogin:
    def test_requires_second_factor(self, api, mfa_user):
        user, _ = mfa_user
        first = api.post(
            reverse("auth-login"), {"email": user.email, "password": PASSWORD}, format="json"
        )
        assert first.status_code == 200
        body = first.json()
        assert body["mfa_required"] is True
        assert "access" not in body
        assert "refresh_token" not in first.cookies

        bad = api.post(
            reverse("auth-login-mfa"),
            {"mfa_token": body["mfa_token"], "code": "123456"},
            format="json",
        )
        assert bad.status_code == 401
        ok = api.post(
            reverse("auth-login-mfa"),
            {"mfa_token": body["mfa_token"], "code": current_code(user)},
            format="json",
        )
        assert ok.status_code == 200
        assert ok.json()["access"]
        assert SecurityEvent.objects.filter(user=user, type="mfa_failed").count() == 1

    def test_recovery_code_single_use(self, api, mfa_user):
        user, codes = mfa_user
        token = mfa.make_login_token(user)
        url = reverse("auth-login-mfa")
        assert (
            api.post(url, {"mfa_token": token, "code": codes[0].lower()}, format="json").status_code
            == 200
        )
        assert (
            api.post(url, {"mfa_token": token, "code": codes[0]}, format="json").status_code == 401
        )
        assert mfa.remaining_recovery_codes(user) == 9

    def test_tampered_token_rejected(self, api, mfa_user):
        user, _ = mfa_user
        response = api.post(
            reverse("auth-login-mfa"),
            {"mfa_token": mfa.make_login_token(user) + "x", "code": current_code(user)},
            format="json",
        )
        assert response.status_code == 401


def test_disable_requires_password_and_code(auth_api, mfa_user):
    user, _ = mfa_user
    url = reverse("mfa-disable")
    assert (
        auth_api.post(
            url, {"password": "mala", "code": current_code(user)}, format="json"
        ).status_code
        == 400
    )
    assert (
        auth_api.post(
            url, {"password": PASSWORD, "code": next_code(user)}, format="json"
        ).status_code
        == 204
    )
    user.refresh_from_db()
    assert not user.mfa_enabled and user.mfa_secret == ""


def test_tenant_requiring_mfa_blocks_users_without_it(user, tenant, membership):
    tenant.require_mfa = True
    tenant.save()
    response = client_for(user, tenant).get(reverse("tenant-current"))
    assert response.status_code == 403
    assert response.json()["code"] == "mfa_setup_required"
    mfa.start_setup(user)
    mfa.enable(user)
    assert client_for(user, tenant).get(reverse("tenant-current")).status_code == 200


def test_login_events_recorded(api, user):
    api.post(reverse("auth-login"), {"email": user.email, "password": "mala"}, format="json")
    api.post(reverse("auth-login"), {"email": user.email, "password": PASSWORD}, format="json")
    types = list(SecurityEvent.objects.order_by("created_at").values_list("type", flat=True))
    assert types == ["login_failed", "login_success"]


def test_admin_without_mfa_cannot_require_it(owner_api, user):
    url = reverse("tenant-current")
    assert owner_api.patch(url, {"require_mfa": True}, format="json").status_code == 400
    mfa.start_setup(user)
    mfa.enable(user)
    assert owner_api.patch(url, {"require_mfa": True}, format="json").status_code == 200
