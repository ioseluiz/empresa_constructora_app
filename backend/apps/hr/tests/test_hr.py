from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.core.tenancy import tenant_context
from apps.hr.models import Employee, EmploymentContract, ProjectAssignment, SalaryRecord
from apps.hr.services import create_contract, create_employee
from apps.iam.services import set_member_assignments
from apps.organization.models import CBACategory, CostCenter, Position
from apps.organization.services import bootstrap_organization
from apps.projects.services import create_project
from apps.tenants.models import Membership
from conftest import client_for, make_member

pytestmark = pytest.mark.django_db

EMPLOYEE = {
    "first_name": "Carlos",
    "last_name": "Batista",
    "id_number": "8-123-4567",
    "css_number": "123-4567",
    "hire_date": "2026-01-05",
    "payment_method": "ach",
    "bank": "banco_general",
    "account_type": "savings",
    "account_number": "0401234567",
}


@pytest.fixture
def org(tenant):
    bootstrap_organization(tenant, years=(2026,))
    with tenant_context(tenant):
        return {
            "p1": create_project(code="P-1", name="Torre", status="active"),
            "p2": create_project(code="P-2", name="Puente", status="active"),
            "alb": Position.objects.get(code="ALB"),
            "oc": CostCenter.objects.get(code="OC"),
        }


def new_employee(tenant, **extra):
    data = {**EMPLOYEE, "hire_date": date(2026, 1, 5), **extra}
    with tenant_context(tenant):
        return create_employee(**data)


def contract_payload(employee, org, **extra):
    return {
        "employee": str(employee.pk),
        "contract_type": "project",
        "start_date": "2026-01-05",
        "position": str(org["alb"].pk),
        "project": str(org["p1"].pk),
        "pay_frequency": "weekly",
        "pay_basis": "hourly",
        "initial_amount": "4.5500",
        **extra,
    }


class TestEmployee:
    def test_create_assigns_code_and_audits(self, owner_api, tenant, org):
        response = owner_api.post(reverse("employee-list"), EMPLOYEE, format="json")
        assert response.status_code == 201, response.json()
        body = response.json()
        assert body["code"] == "E-0001"
        assert body["full_name"] == "Carlos Batista"
        assert body["status"] == "active"
        second = owner_api.post(
            reverse("employee-list"), {**EMPLOYEE, "id_number": "8-1-2"}, format="json"
        )
        assert second.json()["code"] == "E-0002"
        with tenant_context(tenant):
            assert AuditLog.objects.filter(object_type="hr.employee", action="create").count() == 2

    @pytest.mark.parametrize(
        "cedula", ["8-123-4567", "4PI-12-345", "E-8-123456", "PE-1-22", "10-1-1"]
    )
    def test_valid_cedulas(self, owner_api, org, cedula):
        response = owner_api.post(
            reverse("employee-list"), {**EMPLOYEE, "id_number": cedula}, format="json"
        )
        assert response.status_code == 201, response.json()

    @pytest.mark.parametrize("cedula", ["8123456", "14-1-1", "X-1-1", "8-12345-1"])
    def test_invalid_cedulas(self, owner_api, org, cedula):
        response = owner_api.post(
            reverse("employee-list"), {**EMPLOYEE, "id_number": cedula}, format="json"
        )
        assert response.status_code == 400
        assert "id_number" in response.json()

    def test_passport_skips_cedula_format(self, owner_api, org):
        payload = {**EMPLOYEE, "id_type": "passport", "id_number": "AB123456"}
        assert owner_api.post(reverse("employee-list"), payload, format="json").status_code == 201

    def test_duplicate_id_rejected(self, owner_api, tenant, org):
        new_employee(tenant)
        response = owner_api.post(reverse("employee-list"), EMPLOYEE, format="json")
        assert response.status_code == 400
        assert "id_number" in response.json()

    def test_ach_requires_bank_account(self, owner_api, org):
        payload = {**EMPLOYEE, "account_number": ""}
        response = owner_api.post(reverse("employee-list"), payload, format="json")
        assert response.status_code == 400
        assert "account_number" in response.json()
        cash = {**payload, "payment_method": "cash", "bank": "", "account_type": ""}
        assert owner_api.post(reverse("employee-list"), cash, format="json").status_code == 201

    def test_employees_cannot_be_deleted(self, owner_api, tenant, org):
        employee = new_employee(tenant)
        url = reverse("employee-detail", args=[employee.pk])
        assert owner_api.delete(url).status_code == 405

    def test_isolated_between_tenants(self, owner_api, other_tenant, org):
        bootstrap_organization(other_tenant, years=())
        new_employee(other_tenant)
        assert owner_api.get(reverse("employee-list")).json()["count"] == 0


class TestContracts:
    def test_project_contract_creates_salary_and_assignment(self, owner_api, tenant, org):
        employee = new_employee(tenant)
        response = owner_api.post(
            reverse("contract-list"), contract_payload(employee, org), format="json"
        )
        assert response.status_code == 201, response.json()
        body = response.json()
        assert body["cost_center_code"] == "P-1"
        assert body["current_salary"]["amount"] == "4.5500"
        with tenant_context(tenant):
            assignment = ProjectAssignment.objects.get(employee=employee)
            assert assignment.project == org["p1"]
            assert assignment.start_date == date(2026, 1, 5)
        employees = owner_api.get(reverse("employee-list"), {"project": str(org["p1"].pk)})
        assert [e["code"] for e in employees.json()["results"]] == [employee.code]
        assert employees.json()["results"][0]["current_position"] == "Albañil"

    def test_office_contract_defaults_to_head_office(self, owner_api, tenant, org):
        employee = new_employee(tenant)
        payload = contract_payload(
            employee,
            org,
            contract_type="indefinite",
            project=None,
            pay_frequency="biweekly",
            pay_basis="monthly",
            initial_amount="1200",
        )
        response = owner_api.post(reverse("contract-list"), payload, format="json")
        assert response.status_code == 201, response.json()
        assert response.json()["cost_center_code"] == "OC"

    @pytest.mark.parametrize(
        ("extra", "field"),
        [
            ({"contract_type": "fixed_term", "end_date": None}, "end_date"),
            ({"project": None}, "project"),
            ({"start_date": "2025-12-01"}, "start_date"),
            ({"initial_amount": None}, "amount"),
            ({"initial_amount": None, "initial_uses_cba_rate": True}, "uses_cba_rate"),
        ],
    )
    def test_validation(self, owner_api, tenant, org, extra, field):
        employee = new_employee(tenant)
        response = owner_api.post(
            reverse("contract-list"), contract_payload(employee, org, **extra), format="json"
        )
        assert response.status_code == 400
        assert field in response.json(), response.json()

    def test_overlapping_contracts_rejected(self, owner_api, tenant, org):
        employee = new_employee(tenant)
        url = reverse("contract-list")
        assert (
            owner_api.post(url, contract_payload(employee, org), format="json").status_code == 201
        )
        again = owner_api.post(
            url, contract_payload(employee, org, start_date="2026-06-01"), format="json"
        )
        assert again.status_code == 400
        assert "start_date" in again.json()

    def test_database_rejects_overlap(self, tenant, org):
        employee = new_employee(tenant)
        common = {
            "employee": employee,
            "contract_type": "indefinite",
            "position": org["alb"],
            "pay_frequency": "monthly",
            "pay_basis": "monthly",
            "initial_amount": Decimal("900"),
            "uses_cba_rate": False,
        }
        with tenant_context(tenant):
            create_contract(start_date=date(2026, 1, 5), end_date=date(2026, 3, 31), **common)
            create_contract(start_date=date(2026, 4, 1), **common)  # contiguo: permitido
            with pytest.raises(IntegrityError), transaction.atomic():
                EmploymentContract.objects.create(
                    employee=employee,
                    contract_type="indefinite",
                    position=org["alb"],
                    cost_center=org["oc"],
                    pay_frequency="monthly",
                    pay_basis="monthly",
                    start_date=date(2026, 3, 31),
                )

    def test_cba_contract_uses_position_category_and_cba_rate(self, owner_api, tenant, org):
        employee = new_employee(tenant)
        payload = contract_payload(
            employee, org, applies_cba=True, initial_amount=None, initial_uses_cba_rate=True
        )
        response = owner_api.post(reverse("contract-list"), payload, format="json")
        assert response.status_code == 201, response.json()
        body = response.json()
        assert body["cba_category_name"] == "Albañil"
        assert body["current_salary"] == {
            **body["current_salary"],
            "amount": None,
            "uses_cba_rate": True,
        }
        with tenant_context(tenant):
            assert EmploymentContract.objects.get().cba_category == CBACategory.objects.get(
                code="ALB"
            )

    def test_salary_history_and_effective_dating(self, owner_api, tenant, org):
        employee = new_employee(tenant)
        cid = owner_api.post(
            reverse("contract-list"), contract_payload(employee, org), format="json"
        ).json()["id"]
        raise_ = owner_api.post(
            reverse("salary-list"),
            {"contract": cid, "valid_from": "2026-07-01", "amount": "5.00", "reason": "Aumento"},
            format="json",
        )
        assert raise_.status_code == 201, raise_.json()
        dup = owner_api.post(
            reverse("salary-list"),
            {"contract": cid, "valid_from": "2026-07-01", "amount": "6.00"},
            format="json",
        )
        assert dup.status_code == 400
        before = owner_api.post(
            reverse("salary-list"),
            {"contract": cid, "valid_from": "2025-12-31", "amount": "6.00"},
            format="json",
        )
        assert before.status_code == 400
        with tenant_context(tenant):
            contract = EmploymentContract.objects.get(pk=cid)
            assert contract.salary_on(date(2026, 6, 30)).amount == Decimal("4.55")
            assert contract.salary_on(date(2026, 7, 1)).amount == Decimal("5.00")
            assert SalaryRecord.objects.count() == 2
        history = owner_api.get(reverse("salary-list"), {"contract": cid}).json()
        assert [r["valid_from"] for r in history] == ["2026-07-01", "2026-01-05"]

    def test_end_contract_retires_employee(self, owner_api, tenant, org):
        employee = new_employee(tenant)
        cid = owner_api.post(
            reverse("contract-list"), contract_payload(employee, org), format="json"
        ).json()["id"]
        response = owner_api.post(
            reverse("contract-end", args=[cid]),
            {"end_date": "2026-10-31", "reason": "Fin de etapa de estructura"},
            format="json",
        )
        assert response.status_code == 200, response.json()
        assert response.json()["status"] == "ended"
        with tenant_context(tenant):
            employee.refresh_from_db()
            assert employee.status == Employee.Status.TERMINATED
            assert employee.termination_date == date(2026, 10, 31)
            assert ProjectAssignment.objects.get(employee=employee).end_date == date(2026, 10, 31)
        edit = owner_api.patch(
            reverse("contract-detail", args=[cid]), {"notes": "x"}, format="json"
        )
        assert edit.status_code == 403
        # Recontratación: vuelve a quedar activo.
        rehire = owner_api.post(
            reverse("contract-list"),
            contract_payload(employee, org, start_date="2026-11-15"),
            format="json",
        )
        assert rehire.status_code == 201, rehire.json()
        with tenant_context(tenant):
            employee.refresh_from_db()
            assert (employee.status, employee.termination_date) == ("active", None)


class TestAssignments:
    def test_overlap_same_project_rejected_other_project_allowed(self, owner_api, tenant, org):
        employee = new_employee(tenant)
        url = reverse("assignment-list")
        base = {"employee": str(employee.pk), "start_date": "2026-02-01"}
        first = owner_api.post(url, {**base, "project": str(org["p1"].pk)}, format="json")
        assert first.status_code == 201, first.json()
        again = owner_api.post(
            url, {**base, "project": str(org["p1"].pk), "start_date": "2026-03-01"}, format="json"
        )
        assert again.status_code == 400
        other = owner_api.post(url, {**base, "project": str(org["p2"].pk)}, format="json")
        assert other.status_code == 201
        detail = owner_api.get(reverse("employee-detail", args=[employee.pk])).json()
        assert sorted(p["code"] for p in detail["current_projects"]) == ["P-1", "P-2"]


class TestProjectScopeAndSalaryPrivacy:
    @pytest.fixture
    def jefe(self, tenant, roles, org):
        user = make_member(tenant, "jefe@obra.pa", [], roles)
        m = Membership.objects.get(user=user)
        with tenant_context(tenant):
            set_member_assignments(m, [(roles["Jefe de proyecto"], [org["p1"]])])
        return client_for(user, tenant)

    @pytest.fixture
    def staff(self, tenant, org):
        a, b = new_employee(tenant), new_employee(tenant, id_number="8-2-2", code="E-0002")
        with tenant_context(tenant):
            ProjectAssignment.objects.create(
                employee=a, project=org["p1"], start_date=date(2026, 1, 5)
            )
            ProjectAssignment.objects.create(
                employee=b, project=org["p2"], start_date=date(2026, 1, 5)
            )
        return a, b

    def test_scoped_role_sees_only_its_project_staff(self, jefe, staff):
        a, b = staff
        rows = jefe.get(reverse("employee-list")).json()["results"]
        assert [r["id"] for r in rows] == [str(a.pk)]
        assert jefe.get(reverse("employee-detail", args=[b.pk])).status_code == 404

    def test_bank_data_hidden_without_salary_permission(self, jefe, owner_api, staff):
        a, _ = staff
        row = jefe.get(reverse("employee-detail", args=[a.pk])).json()
        assert "account_number" not in row and "bank" not in row
        assert "account_number" in owner_api.get(reverse("employee-detail", args=[a.pk])).json()

    def test_salaries_require_permission(self, jefe, owner_api, tenant, org, staff):
        a, _ = staff
        cid = owner_api.post(
            reverse("contract-list"),
            contract_payload(a, org, start_date="2026-01-05"),
            format="json",
        ).json()["id"]
        assert jefe.get(reverse("salary-list"), {"contract": cid}).status_code == 403
        contract = jefe.get(reverse("contract-detail", args=[cid])).json()
        assert contract["current_salary"] is None

    def test_scoped_role_cannot_create_employees(self, tenant, roles, org):
        role = roles["Jefe de proyecto"]
        with tenant_context(tenant):
            role.permissions = [*role.permissions, "hr.employee.manage"]
            role.save()
        user = make_member(tenant, "rh-obra@obra.pa", [], roles)
        m = Membership.objects.get(user=user)
        with tenant_context(tenant):
            set_member_assignments(m, [(role, [org["p1"]])])
        api = client_for(user, tenant)
        assert api.post(reverse("employee-list"), EMPLOYEE, format="json").status_code == 403


PDF = b"%PDF-1.4\n%fake\n"


class TestDocuments:
    def upload(self, api, employee, content=PDF, content_type="application/pdf", name="cedula.pdf"):
        return api.post(
            reverse("document-list"),
            {
                "employee": str(employee.pk),
                "kind": "id_copy",
                "file": SimpleUploadedFile(name, content, content_type=content_type),
            },
            format="multipart",
        )

    def test_upload_and_download(self, owner_api, tenant, org):
        employee = new_employee(tenant)
        response = self.upload(owner_api, employee)
        assert response.status_code == 201, response.json()
        body = response.json()
        assert body["original_name"] == "cedula.pdf" and body["size"] == len(PDF)
        assert "file" not in body
        with tenant_context(tenant):
            stored = employee.documents.get().file.name
        assert "cedula" not in stored and stored.startswith(f"tenants/{tenant.pk}/")
        download = owner_api.get(reverse("document-download", args=[body["id"]]))
        assert download.status_code == 200
        assert b"".join(download.streaming_content) == PDF
        assert download["Cache-Control"] == "private, no-store"

    def test_rejects_disguised_or_unsupported_files(self, owner_api, tenant, org):
        employee = new_employee(tenant)
        fake = self.upload(owner_api, employee, content=b"MZ\x90\x00exe")
        assert fake.status_code == 400
        exe = self.upload(
            owner_api, employee, content=b"MZ", content_type="application/x-msdownload"
        )
        assert exe.status_code == 400

    def test_delete_removes_file(self, owner_api, tenant, org):
        employee = new_employee(tenant)
        doc_id = self.upload(owner_api, employee).json()["id"]
        assert owner_api.delete(reverse("document-detail", args=[doc_id])).status_code == 204
        with tenant_context(tenant):
            assert not employee.documents.exists()
            assert AuditLog.objects.filter(
                object_type="hr.employeedocument", action="delete"
            ).exists()
