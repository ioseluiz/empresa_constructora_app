import re

import pytest
from django.core import mail
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.cookies import REFRESH_COOKIE
from apps.accounts.models import User
from conftest import PASSWORD

pytestmark = pytest.mark.django_db


def login(api: APIClient, email: str = "ana@constructora.pa", password: str = PASSWORD):
    return api.post(reverse("auth-login"), {"email": email, "password": password}, format="json")


class TestLogin:
    def test_ok_returns_access_and_sets_httponly_refresh_cookie(self, api, user, membership):
        response = login(api)
        assert response.status_code == 200
        body = response.json()
        assert body["access"]
        assert body["user"]["email"] == "ana@constructora.pa"
        assert body["user"]["memberships"][0]["tenant_slug"] == "istmo"
        cookie = response.cookies[REFRESH_COOKIE]
        assert cookie["httponly"]
        assert cookie["path"] == "/api/v1/auth/"
        assert "refresh" not in body  # nunca expuesto a JavaScript

    def test_email_is_case_insensitive(self, api, user):
        assert login(api, email="ANA@Constructora.PA").status_code == 200

    @pytest.mark.parametrize(
        ("email", "password"),
        [("ana@constructora.pa", "incorrecta"), ("nadie@constructora.pa", PASSWORD)],
    )
    def test_bad_credentials_same_generic_error(self, api, user, email, password):
        response = login(api, email, password)
        assert response.status_code == 401
        assert response.json()["detail"] == "Correo o contraseña incorrectos."

    def test_inactive_user_rejected(self, api, user):
        user.is_active = False
        user.save()
        assert login(api).status_code == 401


class TestRefreshAndLogout:
    def test_refresh_rotates_token(self, api, user):
        first = login(api).cookies[REFRESH_COOKIE].value
        response = api.post(reverse("auth-refresh"))
        assert response.status_code == 200
        assert response.json()["access"]
        second = response.cookies[REFRESH_COOKIE].value
        assert second != first

        # El token anterior quedó en lista negra: reutilizarlo falla.
        api.cookies[REFRESH_COOKIE] = first
        assert api.post(reverse("auth-refresh")).status_code == 401

    def test_refresh_without_cookie(self, api):
        assert api.post(reverse("auth-refresh")).status_code == 401

    def test_logout_invalidates_refresh(self, api, user):
        token = login(api).cookies[REFRESH_COOKIE].value
        response = api.post(reverse("auth-logout"))
        assert response.status_code == 204
        assert response.cookies[REFRESH_COOKIE].value == ""
        api.cookies[REFRESH_COOKIE] = token
        assert api.post(reverse("auth-refresh")).status_code == 401


class TestMe:
    def test_requires_auth(self, api):
        assert api.get(reverse("auth-me")).status_code == 401

    def test_returns_profile(self, auth_api, membership):
        body = auth_api.get(reverse("auth-me")).json()
        assert body["full_name"] == "Ana"
        assert len(body["memberships"]) == 1

    def test_inactive_memberships_hidden(self, auth_api, membership):
        membership.is_active = False
        membership.save()
        assert auth_api.get(reverse("auth-me")).json()["memberships"] == []

    def test_update_name_but_not_email(self, auth_api, user):
        response = auth_api.patch(
            reverse("auth-me"), {"last_name": "Pérez", "email": "x@x.com"}, format="json"
        )
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.last_name == "Pérez"
        assert user.email == "ana@constructora.pa"


class TestPasswordReset:
    def _reset_link_params(self) -> tuple[str, str]:
        match = re.search(r"uid=([\w-]+)&token=([\w-]+)", str(mail.outbox[0].body))
        assert match
        return match.group(1), match.group(2)

    def test_full_flow(self, api, user):
        response = api.post(reverse("password-reset"), {"email": user.email}, format="json")
        assert response.status_code == 204
        assert len(mail.outbox) == 1
        uid, token = self._reset_link_params()

        new_password = "Nueva-Clave-Obra-99"
        response = api.post(
            reverse("password-reset-confirm"),
            {"uid": uid, "token": token, "new_password": new_password},
            format="json",
        )
        assert response.status_code == 204
        assert login(api, password=new_password).status_code == 200

        # El token es de un solo uso: cambia al cambiar la contraseña.
        response = api.post(
            reverse("password-reset-confirm"),
            {"uid": uid, "token": token, "new_password": "Otra-Clave-Obra-77"},
            format="json",
        )
        assert response.status_code == 400

    def test_unknown_email_same_response_no_mail(self, api, db):
        response = api.post(reverse("password-reset"), {"email": "x@y.com"}, format="json")
        assert response.status_code == 204
        assert mail.outbox == []

    def test_weak_password_rejected(self, api, user):
        api.post(reverse("password-reset"), {"email": user.email}, format="json")
        uid, token = self._reset_link_params()
        response = api.post(
            reverse("password-reset-confirm"),
            {"uid": uid, "token": token, "new_password": "12345678"},
            format="json",
        )
        assert response.status_code == 400

    def test_invalid_uid(self, api, db):
        response = api.post(
            reverse("password-reset-confirm"),
            {"uid": "basura", "token": "x", "new_password": "Nueva-Clave-Obra-99"},
            format="json",
        )
        assert response.status_code == 400


class TestPasswordChange:
    def test_change(self, auth_api, user):
        response = auth_api.post(
            reverse("password-change"),
            {"current_password": PASSWORD, "new_password": "Nueva-Clave-Obra-99"},
            format="json",
        )
        assert response.status_code == 204
        user.refresh_from_db()
        assert user.check_password("Nueva-Clave-Obra-99")

    def test_wrong_current(self, auth_api):
        response = auth_api.post(
            reverse("password-change"),
            {"current_password": "mala", "new_password": "Nueva-Clave-Obra-99"},
            format="json",
        )
        assert response.status_code == 400


def test_user_manager_normalizes_email(db):
    u = User.objects.create_user("Luis@Obra.PA", PASSWORD)
    assert u.email == "luis@obra.pa"
    assert User.objects.create_superuser("root@obra.pa", PASSWORD).is_staff
