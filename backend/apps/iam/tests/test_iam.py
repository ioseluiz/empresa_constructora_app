import re

import pytest
from django.core import mail
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.core.tenancy import tenant_context
from apps.iam.catalog import DEFAULT_ROLES, PERMISSION_CODES
from apps.iam.models import Invitation, Role
from apps.tenants.models import Membership
from apps.tenants.services import create_tenant
from conftest import PASSWORD, client_for, make_member

pytestmark = pytest.mark.django_db


def test_default_roles_only_use_known_permissions():
    for spec in DEFAULT_ROLES.values():
        assert set(spec["permissions"]) <= PERMISSION_CODES


def test_create_tenant_seeds_default_roles(db):
    tenant, _ = create_tenant(
        name="Obra Nueva", owner_email="dueno@obra.pa", owner_password=PASSWORD
    )
    with tenant_context(tenant):
        assert set(Role.objects.values_list("name", flat=True)) == set(DEFAULT_ROLES)


class TestMyAccess:
    def test_owner_has_everything(self, owner_api):
        body = owner_api.get(reverse("iam-me")).json()
        assert body["is_owner"] is True
        assert set(body["permissions"]) == PERMISSION_CODES

    def test_member_gets_union_of_roles(self, tenant, roles):
        member = make_member(tenant, "sup@obra.pa", ["Supervisor de obra", "Auditor"], roles)
        body = client_for(member, tenant).get(reverse("iam-me")).json()
        assert "timeclock.manual" in body["permissions"]
        assert "audit.view" in body["permissions"]
        assert "users.manage" not in body["permissions"]
        assert sorted(body["roles"]) == ["Auditor", "Supervisor de obra"]


class TestRoles:
    def test_supervisor_cannot_list_roles(self, tenant, roles):
        member = make_member(tenant, "sup@obra.pa", ["Supervisor de obra"], roles)
        assert client_for(member, tenant).get(reverse("role-list")).status_code == 403

    def test_crud_with_audit(self, owner_api, tenant):
        response = owner_api.post(
            reverse("role-list"),
            {"name": "Bodeguero", "permissions": ["projects.view", "projects.view"]},
            format="json",
        )
        assert response.status_code == 201, response.json()
        role_id = response.json()["id"]
        assert response.json()["permissions"] == ["projects.view"]

        response = owner_api.patch(
            reverse("role-detail", args=[role_id]),
            {"permissions": ["projects.view", "hr.employee.view"]},
            format="json",
        )
        assert response.status_code == 200
        assert owner_api.delete(reverse("role-detail", args=[role_id])).status_code == 204

        with tenant_context(tenant):
            actions = list(
                AuditLog.objects.filter(object_type="iam.role").values_list("action", flat=True)
            )
        assert sorted(actions) == ["create", "delete", "update"]

    def test_unknown_permission_rejected(self, owner_api):
        response = owner_api.post(
            reverse("role-list"), {"name": "X", "permissions": ["hackear.todo"]}, format="json"
        )
        assert response.status_code == 400

    def test_duplicate_name_rejected(self, owner_api):
        response = owner_api.post(reverse("role-list"), {"name": "auditor"}, format="json")
        assert response.status_code == 400

    def test_cannot_delete_assigned_role(self, owner_api, tenant, roles):
        make_member(tenant, "aud@obra.pa", ["Auditor"], roles)
        response = owner_api.delete(reverse("role-detail", args=[roles["Auditor"].pk]))
        assert response.status_code == 400

    def test_roles_isolated_between_tenants(self, owner_api, other_tenant):
        create_tenant(name="Otra", owner_email="otro@x.pa", owner_password=PASSWORD)
        names = [r["name"] for r in owner_api.get(reverse("role-list")).json()]
        assert len(names) == len(DEFAULT_ROLES)


class TestMembers:
    def test_list_and_change_roles(self, owner_api, tenant, roles):
        member = make_member(tenant, "plan@obra.pa", ["Planillero"], roles)
        m = Membership.objects.get(user=member)
        response = owner_api.patch(
            reverse("member-detail", args=[m.pk]),
            {"role_ids": [str(roles["Contador"].pk)]},
            format="json",
        )
        assert response.status_code == 200, response.json()
        assert [r["name"] for r in response.json()["roles"]] == ["Contador"]
        with tenant_context(tenant):
            log = AuditLog.objects.get(object_type="tenants.membership")
        assert log.changes["roles"] == {"antes": ["Planillero"], "despues": ["Contador"]}

    def test_cannot_modify_self_or_owner(self, owner_api, membership):
        response = owner_api.patch(
            reverse("member-detail", args=[membership.pk]), {"is_active": False}, format="json"
        )
        assert response.status_code == 400

    def test_deactivated_member_loses_access(self, owner_api, tenant, roles):
        member = make_member(tenant, "aud@obra.pa", ["Auditor"], roles)
        m = Membership.objects.get(user=member)
        owner_api.patch(reverse("member-detail", args=[m.pk]), {"is_active": False}, format="json")
        assert client_for(member, tenant).get(reverse("iam-me")).status_code == 403

    def test_cannot_assign_role_from_other_tenant(self, owner_api, tenant, roles):
        other, _ = create_tenant(name="Otra", owner_email="otro@x.pa", owner_password=PASSWORD)
        with tenant_context(other):
            foreign_role = Role.objects.first()
        member = make_member(tenant, "aud@obra.pa", ["Auditor"], roles)
        m = Membership.objects.get(user=member)
        response = owner_api.patch(
            reverse("member-detail", args=[m.pk]),
            {"role_ids": [str(foreign_role.pk)]},
            format="json",
        )
        assert response.status_code == 400

    def test_members_of_other_tenant_not_visible(self, owner_api):
        create_tenant(name="Otra", owner_email="otro@x.pa", owner_password=PASSWORD)
        emails = [
            m["user"]["email"] for m in owner_api.get(reverse("member-list")).json()["results"]
        ]
        assert emails == ["ana@constructora.pa"]


class TestInvitations:
    def _token(self) -> str:
        match = re.search(r"token=([\w-]+)", str(mail.outbox[-1].body))
        assert match
        return match.group(1)

    def _invite(self, api, email, role):
        return api.post(
            reverse("invitation-list"), {"email": email, "role_ids": [str(role.pk)]}, format="json"
        )

    def test_new_user_full_flow(self, owner_api, api, tenant, roles):
        response = self._invite(owner_api, "Nuevo@Obra.pa", roles["Planillero"])
        assert response.status_code == 201, response.json()
        token = self._token()

        info = api.get(reverse("invitation-public", args=[token])).json()
        assert info == {
            "email": "nuevo@obra.pa",
            "tenant_name": "Constructora Istmo",
            "user_exists": False,
        }
        response = api.post(
            reverse("invitation-accept", args=[token]),
            {"first_name": "Luis", "last_name": "Gómez", "password": "Clave-Nueva-Obra-1"},
            format="json",
        )
        assert response.status_code == 201, response.json()
        assert response.json()["access"]
        assert response.cookies["refresh_token"]["httponly"]

        m = Membership.objects.get(user__email="nuevo@obra.pa", tenant=tenant)
        with tenant_context(tenant):
            assert [a.role.name for a in m.role_assignments.all()] == ["Planillero"]
            assert Invitation.objects.get().status == "accepted"
            accepted = AuditLog.objects.get(action="accept")
            assert accepted.actor_email == "nuevo@obra.pa"
        # El token ya no sirve
        assert api.get(reverse("invitation-public", args=[token])).status_code == 404

    def test_existing_user_must_confirm_password(self, owner_api, api, tenant, roles):
        create_tenant(name="Otra", owner_email="contador@x.pa", owner_password=PASSWORD)
        self._invite(owner_api, "contador@x.pa", roles["Contador"])
        token = self._token()
        assert api.get(reverse("invitation-public", args=[token])).json()["user_exists"] is True
        bad = api.post(reverse("invitation-accept", args=[token]), {"password": "x"}, format="json")
        assert bad.status_code == 400
        ok = api.post(
            reverse("invitation-accept", args=[token]), {"password": PASSWORD}, format="json"
        )
        assert ok.status_code == 201
        assert len(ok.json()["user"]["memberships"]) == 2

    def test_cannot_invite_existing_member_or_twice(self, owner_api, roles):
        assert self._invite(owner_api, "ana@constructora.pa", roles["Auditor"]).status_code == 400
        assert self._invite(owner_api, "x@obra.pa", roles["Auditor"]).status_code == 201
        assert self._invite(owner_api, "x@obra.pa", roles["Auditor"]).status_code == 400

    def test_revoke_and_resend(self, owner_api, api, roles):
        inv_id = self._invite(owner_api, "x@obra.pa", roles["Auditor"]).json()["id"]
        first = self._token()
        assert owner_api.post(reverse("invitation-resend", args=[inv_id])).status_code == 200
        second = self._token()
        assert first != second
        assert api.get(reverse("invitation-public", args=[first])).status_code == 404
        assert owner_api.delete(reverse("invitation-detail", args=[inv_id])).status_code == 204
        assert api.get(reverse("invitation-public", args=[second])).status_code == 404

    def test_requires_users_manage(self, tenant, roles):
        member = make_member(tenant, "aud@obra.pa", ["Auditor"], roles)
        response = self._invite(client_for(member, tenant), "x@obra.pa", roles["Auditor"])
        assert response.status_code == 403

    def test_token_stored_hashed(self, owner_api, tenant, roles):
        self._invite(owner_api, "x@obra.pa", roles["Auditor"])
        token = self._token()
        with tenant_context(tenant):
            assert Invitation.objects.get().token_hash != token


class TestTenantProfile:
    def test_auditor_cannot_edit_but_admin_role_can(self, tenant, roles):
        auditor = make_member(tenant, "aud@obra.pa", ["Auditor"], roles)
        admin = make_member(tenant, "adm@obra.pa", ["Administrador"], roles)
        url = reverse("tenant-current")
        assert (
            client_for(auditor, tenant).patch(url, {"ruc": "1"}, format="json").status_code == 403
        )
        assert client_for(admin, tenant).patch(url, {"ruc": "1"}, format="json").status_code == 200
