from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.attendance.models import TimeEntry
from apps.core.tenancy import tenant_context
from apps.hr.models import ProjectAssignment, SalaryRecord
from apps.hr.services import create_contract, create_employee
from apps.organization.models import CBACategory, CBAWageRate, CostCenter, Position
from apps.organization.services import bootstrap_organization
from apps.payroll.calculator import calculate
from apps.payroll.models import PayrollConcept, PayrollSettings, RecurringDeduction
from apps.payroll.services import bootstrap_payroll
from apps.projects.services import create_project
from apps.timeclock.models import WorkDay
from apps.timeclock.services import bootstrap_timeclock
from conftest import client_for, make_member

pytestmark = pytest.mark.django_db
D = Decimal


@pytest.fixture
def setup(tenant):
    bootstrap_organization(tenant, years=(2026,))
    with tenant_context(tenant):
        bootstrap_timeclock()
        bootstrap_payroll()
        PayrollSettings.objects.update(occupational_risk_rate=D("0.0567"))
        project = create_project(code="P-1", name="Torre", status="active")
        alb = Position.objects.get(code="ALB")
        oc = CostCenter.objects.get(code="OC")
        worker = create_employee(
            code="E-1",
            first_name="Ana",
            last_name="Ruiz",
            id_number="8-1-1",
            hire_date=date(2026, 1, 5),
            payment_method="cash",
        )
        clerk = create_employee(
            code="E-2",
            first_name="Beto",
            last_name="Sanz",
            id_number="8-2-2",
            hire_date=date(2026, 1, 5),
            payment_method="cash",
        )
        ProjectAssignment.objects.create(
            employee=worker, project=project, start_date=date(2026, 1, 5)
        )
        category = CBACategory.objects.get(code="ALB")
        CBAWageRate.objects.create(
            category=category, hourly_rate=D("4.50"), valid_from=date(2026, 1, 1)
        )
        CBAWageRate.objects.create(
            category=category, hourly_rate=D("4.80"), valid_from=date(2026, 11, 18)
        )
        create_contract(
            employee=worker,
            contract_type="project",
            start_date=date(2026, 1, 5),
            position=alb,
            project=project,
            pay_frequency="weekly",
            pay_basis="hourly",
            applies_cba=True,
            cba_category=category,
            initial_amount=None,
            uses_cba_rate=True,
        )
        clerk_contract = create_contract(
            employee=clerk,
            contract_type="indefinite",
            start_date=date(2026, 1, 5),
            position=alb,
            pay_frequency="biweekly",
            pay_basis="monthly",
            initial_amount=D("1000"),
            uses_cba_rate=False,
        )
        # Aumento a mitad de la quincena: 1,000 los días 1-10 y 1,300 los días 11-15.
        SalaryRecord.objects.create(
            contract=clerk_contract, valid_from=date(2026, 11, 11), amount=D("1300")
        )
        for day, rate_day in ((date(2026, 11, 16), "8"), (date(2026, 11, 18), "8")):
            wd = WorkDay.objects.create(
                employee=worker,
                date=day,
                project=project,
                day_kind="regular",
                ordinary_minutes=480,
                status="approved",
            )
            TimeEntry.objects.create(
                employee=worker,
                date=day,
                project=project,
                cost_center=project.cost_center,
                hour_type="ordinary",
                day_kind="regular",
                hours=D(rate_day),
                workday=wd,
            )
        WorkDay.objects.create(
            employee=worker,
            date=date(2026, 11, 17),
            day_kind="regular",
            issues=["missing_out"],
            status="review",
        )
    return {"worker": worker, "clerk": clerk, "project": project, "oc": oc}


def lines(result):
    out: dict[str, Decimal] = {}
    for ln in result.lines:
        out[ln.code] = out.get(ln.code, D("0")) + ln.amount
    return out


def test_hourly_worker_uses_cba_rate_by_date(tenant, setup):
    with tenant_context(tenant):
        r = calculate(setup["worker"], date(2026, 11, 16), date(2026, 11, 22))
    # 8 h × 4.50 (lunes) + 8 h × 4.80 (miércoles, nueva tarifa) = 74.40
    assert lines(r)["HORAS_ORD"] == D("74.40")
    assert any("sin aprobar" in w for w in r.warnings)


def test_monthly_salary_prorated_by_salary_change(tenant, setup):
    with tenant_context(tenant):
        r = calculate(setup["clerk"], date(2026, 11, 1), date(2026, 11, 15))
    # (10 días × 1,000 + 5 días × 1,300) × 0.5 / 15 = 550.00
    assert lines(r)["SALARIO"] == D("550.00")
    assert all(ln.cost_center_id == setup["oc"].pk for ln in r.lines if ln.kind == "employer")


def test_preview_api_and_deductions(owner_api, tenant, setup):
    with tenant_context(tenant):
        prestamo = PayrollConcept.objects.get(code="PRESTAMO")
    created = owner_api.post(
        reverse("recurring-deduction-list"),
        {
            "employee": str(setup["clerk"].pk),
            "concept": str(prestamo.pk),
            "amount_per_period": "50.00",
            "total_amount": "300.00",
            "start_date": "2026-11-01",
            "creditor": "Cooperativa",
        },
        format="json",
    )
    assert created.status_code == 201, created.json()
    response = owner_api.post(
        reverse("payroll-preview"),
        {
            "employee": str(setup["clerk"].pk),
            "period_start": "2026-11-01",
            "period_end": "2026-11-15",
        },
        format="json",
    )
    assert response.status_code == 200, response.json()
    body = response.json()
    by_code = {ln["code"]: ln for ln in body["lines"]}
    assert by_code["SALARIO"]["amount"] == "550.00"
    assert by_code["PRESTAMO"]["amount"] == "50.00"
    assert by_code["CSS_PATRONAL"]["cost_center"] == "OC"
    assert D(body["net"]) == D(body["gross"]) - D(body["deductions"])
    assert "css_employee_rate" in body["parameters"]


def test_preview_without_contract(owner_api, tenant, setup):
    with tenant_context(tenant):
        other = create_employee(
            code="E-9",
            first_name="Sin",
            last_name="Contrato",
            id_number="8-9-9",
            hire_date=date(2026, 1, 5),
            payment_method="cash",
        )
    response = owner_api.post(
        reverse("payroll-preview"),
        {"employee": str(other.pk), "period_start": "2026-11-01", "period_end": "2026-11-15"},
        format="json",
    )
    assert response.status_code == 400 and "contrato" in response.json()["detail"]


def test_legal_order_requires_reference(owner_api, tenant, setup):
    with tenant_context(tenant):
        pension = PayrollConcept.objects.get(code="PENSION_ALIM")
    response = owner_api.post(
        reverse("recurring-deduction-list"),
        {
            "employee": str(setup["clerk"].pk),
            "concept": str(pension.pk),
            "amount_per_period": "40",
            "start_date": "2026-11-01",
        },
        format="json",
    )
    assert response.status_code == 400 and "reference" in response.json()


def test_system_concepts_are_protected(owner_api, tenant, setup):
    with tenant_context(tenant):
        css = PayrollConcept.objects.get(code="CSS")
    url = reverse("payroll-concept-detail", args=[css.pk])
    assert owner_api.patch(url, {"kind": "earning"}, format="json").status_code == 400
    assert owner_api.patch(url, {"accounting_account": "2105"}, format="json").status_code == 200
    assert owner_api.delete(url).status_code == 400


def test_settings_and_permissions(owner_api, tenant, roles, setup):
    url = reverse("payroll-settings")
    assert (
        owner_api.patch(url, {"occupational_risk_rate": "0.0434"}, format="json").status_code == 200
    )
    planillero = client_for(make_member(tenant, "pl@obra.pa", ["Planillero"], roles), tenant)
    assert planillero.get(url).json()["occupational_risk_rate"] == "0.043400"
    assert (
        planillero.patch(url, {"occupational_risk_rate": "0.1"}, format="json").status_code == 403
    )
    preview = planillero.post(
        reverse("payroll-preview"),
        {
            "employee": str(setup["clerk"].pk),
            "period_start": "2026-11-01",
            "period_end": "2026-11-15",
        },
        format="json",
    )
    assert preview.status_code == 200
    jefe = client_for(make_member(tenant, "jefe@obra.pa", ["Jefe de proyecto"], roles), tenant)
    assert jefe.post(reverse("payroll-preview"), {}, format="json").status_code == 403
    params = planillero.get(reverse("legal-parameter-list"), {"key": "isr_brackets"}).json()
    assert params[0]["table"][2]["fixed"] == "5850"


def test_new_tenant_gets_concepts(db):
    from apps.tenants.services import create_tenant
    from conftest import PASSWORD

    new, _ = create_tenant(name="Obra Nueva", owner_email="n@o.pa", owner_password=PASSWORD)
    with tenant_context(new):
        assert PayrollConcept.objects.filter(is_system=True).count() >= 20
        assert PayrollSettings.objects.get().country == "PA"
        assert not RecurringDeduction.objects.exists()
