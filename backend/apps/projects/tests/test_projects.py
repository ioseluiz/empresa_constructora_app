import pytest
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.core.tenancy import tenant_context
from apps.iam.services import permission_scope, set_member_assignments
from apps.organization.models import CostCenter
from apps.projects.models import Project
from apps.projects.services import create_project
from apps.tenants.models import Membership
from conftest import client_for, make_member

pytestmark = pytest.mark.django_db

PAYLOAD = {
    "code": "p-001",
    "name": "Torre Costa del Este",
    "client": "Inversiones del Istmo S.A.",
    "province": "panama",
    "status": "active",
    "start_date": "2026-01-15",
    "estimated_end_date": "2027-06-30",
    "contract_amount": "1250000.00",
}


def test_create_creates_cost_center_and_audit(owner_api, tenant):
    response = owner_api.post(reverse("project-list"), PAYLOAD, format="json")
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["code"] == "P-001"
    assert body["cost_center_code"] == "P-001"
    assert body["contract_amount"] == "1250000.00"
    with tenant_context(tenant):
        cc = CostCenter.objects.get(pk=body["cost_center"])
        assert cc.kind == "project" and cc.name == "Torre Costa del Este"
        assert AuditLog.objects.filter(object_type="projects.project", action="create").exists()


def test_update_syncs_cost_center(owner_api, tenant):
    pid = owner_api.post(reverse("project-list"), PAYLOAD, format="json").json()["id"]
    owner_api.patch(
        reverse("project-detail", args=[pid]),
        {"name": "Torre CDE", "status": "finished"},
        format="json",
    )
    with tenant_context(tenant):
        cc = Project.objects.get(pk=pid).cost_center
        assert (cc.name, cc.is_active) == ("Torre CDE", False)


def test_code_must_be_unique_against_cost_centers(owner_api, tenant):
    with tenant_context(tenant):
        CostCenter.objects.create(code="ADM", name="Administración")
    response = owner_api.post(reverse("project-list"), {**PAYLOAD, "code": "adm"}, format="json")
    assert response.status_code == 400


def test_dates_validated(owner_api):
    response = owner_api.post(
        reverse("project-list"),
        {**PAYLOAD, "start_date": "2027-01-01", "estimated_end_date": "2026-01-01"},
        format="json",
    )
    assert response.status_code == 400


def test_projects_cannot_be_deleted(owner_api):
    pid = owner_api.post(reverse("project-list"), PAYLOAD, format="json").json()["id"]
    assert owner_api.delete(reverse("project-detail", args=[pid])).status_code == 405


class TestProjectScope:
    @pytest.fixture
    def projects(self, tenant):
        with tenant_context(tenant):
            return [
                create_project(code="P-1", name="Uno"),
                create_project(code="P-2", name="Dos"),
            ]

    def _scoped_manager(self, tenant, roles, project):
        user = make_member(tenant, "jefe@obra.pa", [], roles)
        m = Membership.objects.get(user=user)
        with tenant_context(tenant):
            set_member_assignments(m, [(roles["Jefe de proyecto"], [project])])
        return user, m

    def test_scoped_role_sees_only_its_projects(self, tenant, roles, projects):
        user, m = self._scoped_manager(tenant, roles, projects[0])
        with tenant_context(tenant):
            assert permission_scope(m, "projects.view") == frozenset({projects[0].pk})
            assert permission_scope(m, "payroll.view") == frozenset()
        rows = client_for(user, tenant).get(reverse("project-list")).json()["results"]
        assert [r["code"] for r in rows] == ["P-1"]
        other = client_for(user, tenant).get(reverse("project-detail", args=[projects[1].pk]))
        assert other.status_code == 404

    def test_global_role_sees_all(self, tenant, roles, projects):
        user = make_member(tenant, "aud@obra.pa", ["Auditor"], roles)
        rows = client_for(user, tenant).get(reverse("project-list")).json()["results"]
        assert len(rows) == 2

    def test_scoped_manage_cannot_create(self, tenant, roles, projects):
        role = roles["Jefe de proyecto"]
        with tenant_context(tenant):
            role.permissions = [*role.permissions, "projects.manage"]
            role.save()
        user, _ = self._scoped_manager(tenant, roles, projects[0])
        api = client_for(user, tenant)
        assert api.post(reverse("project-list"), PAYLOAD, format="json").status_code == 403
        ok = api.patch(
            reverse("project-detail", args=[projects[0].pk]), {"client": "X"}, format="json"
        )
        assert ok.status_code == 200

    def test_assign_scoped_role_via_api(self, owner_api, tenant, roles, projects):
        user = make_member(tenant, "jefe@obra.pa", [], roles)
        m = Membership.objects.get(user=user)
        response = owner_api.patch(
            reverse("member-detail", args=[m.pk]),
            {
                "set_assignments": [
                    {
                        "role_id": str(roles["Jefe de proyecto"].pk),
                        "project_ids": [str(projects[1].pk)],
                    },
                    {"role_id": str(roles["Auditor"].pk)},
                ]
            },
            format="json",
        )
        assert response.status_code == 200, response.json()
        by_role = {a["role"]["name"]: a["projects"] for a in response.json()["assignments"]}
        assert [p["code"] for p in by_role["Jefe de proyecto"]] == ["P-2"]
        assert by_role["Auditor"] == []
        with tenant_context(tenant):
            log = AuditLog.objects.get(object_type="tenants.membership")
        assert "Jefe de proyecto (P-2)" in log.changes["roles"]["despues"]
