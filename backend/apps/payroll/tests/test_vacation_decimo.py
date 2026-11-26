from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.attendance.models import TimeEntry
from apps.core.tenancy import tenant_context
from apps.hr.models import ProjectAssignment
from apps.hr.services import create_contract, create_employee
from apps.leave.models import VacationRequest
from apps.organization.models import Position
from apps.organization.services import bootstrap_organization
from apps.payroll.models import LegalParameter
from apps.payroll.services import bootstrap_payroll
from apps.projects.services import create_project
from apps.timeclock.models import WorkDay
from apps.timeclock.services import bootstrap_timeclock

pytestmark = pytest.mark.django_db
D = Decimal


@pytest.fixture
def setup(tenant):
    bootstrap_organization(tenant, years=(2026,))
    with tenant_context(tenant):
        bootstrap_timeclock()
        bootstrap_payroll()
        project = create_project(code="P-1", name="Torre", status="active")
        alb = Position.objects.get(code="ALB")
        worker = create_employee(
            code="E-1",
            first_name="Ana",
            last_name="Obra",
            id_number="8-1-1",
            hire_date=date(2026, 1, 5),
            payment_method="cash",
        )
        ProjectAssignment.objects.create(
            employee=worker, project=project, start_date=date(2026, 1, 5)
        )
        create_contract(
            employee=worker,
            contract_type="project",
            start_date=date(2026, 1, 5),
            position=alb,
            project=project,
            pay_frequency="weekly",
            pay_basis="hourly",
            initial_amount=D("5"),
            uses_cba_rate=False,
        )
        clerk = create_employee(
            code="E-2",
            first_name="Ofi",
            last_name="Cina",
            id_number="8-2-2",
            hire_date=date(2026, 1, 5),
            payment_method="cash",
        )
        create_contract(
            employee=clerk,
            contract_type="indefinite",
            start_date=date(2026, 1, 5),
            position=alb,
            pay_frequency="biweekly",
            pay_basis="monthly",
            initial_amount=D("1200"),
            uses_cba_rate=False,
        )
    return {"project": project, "worker": worker, "clerk": clerk}


def run(api, **data):
    created = api.post(reverse("payroll-run-list"), data, format="json")
    assert created.status_code == 201, created.json()
    rid = created.json()["id"]
    calculated = api.post(reverse("payroll-run-calculate", args=[rid])).json()
    return rid, calculated


def items(api, rid):
    lines = api.get(reverse("payroll-run-lines", args=[rid])).json()["results"]
    return {ln["employee_code"]: {i["code"]: i for i in ln["items"]} for ln in lines}


def approved_vacation(tenant, employee, start, end, days, mode):
    with tenant_context(tenant):
        return VacationRequest.objects.create(
            employee=employee,
            start_date=start,
            end_date=end,
            days=days,
            status="approved",
            payment_mode=mode,
        )


def test_vacation_in_regular_payroll_replaces_salary(owner_api, tenant, setup):
    vac = approved_vacation(
        tenant, setup["clerk"], date(2026, 11, 16), date(2026, 11, 25), 10, "payroll"
    )
    rid, calc = run(
        owner_api,
        frequency="biweekly",
        scope="office",
        period_start="2026-11-16",
        period_end="2026-11-30",
        pay_date="2026-11-30",
    )
    got = items(owner_api, rid)["E-2"]
    # Salario de 5 de 15 días: 600 × 5 / 15 = 200; vacaciones 10 × 40.00 (1,200 / 30).
    assert got["SALARIO"]["amount"] == "200.00"
    assert got["VACACIONES"]["amount"] == "400.00"
    assert calc["gross"] == "600.00"
    owner_api.post(reverse("payroll-run-approve", args=[rid]))
    with tenant_context(tenant):
        vac.refresh_from_db()
        assert vac.is_paid and vac.paid_amount == D("400.00")
    # No se vuelve a pagar en la siguiente quincena.
    rid2, _ = run(
        owner_api,
        frequency="biweekly",
        scope="office",
        period_start="2026-12-01",
        period_end="2026-12-15",
        pay_date="2026-12-15",
    )
    assert "VACACIONES" not in items(owner_api, rid2)["E-2"]


def add_hours(employee, project, day, qty):
    wd = WorkDay.objects.create(
        employee=employee, date=day, project=project, day_kind="regular", status="approved"
    )
    TimeEntry.objects.create(
        employee=employee,
        date=day,
        project=project,
        cost_center=project.cost_center,
        hour_type="ordinary",
        day_kind="regular",
        hours=D(qty),
        workday=wd,
    )


def approved_weeks(api, tenant, setup, weeks):
    for start, end in weeks:
        with tenant_context(tenant):
            add_hours(setup["worker"], setup["project"], date.fromisoformat(start), "48")
        rid, _ = run(
            api,
            frequency="weekly",
            scope="project",
            project=str(setup["project"].pk),
            period_start=start,
            period_end=end,
            pay_date=end,
        )
        api.post(reverse("payroll-run-approve", args=[rid]))


def test_separate_vacation_run_uses_higher_of_average_or_current(owner_api, tenant, setup):
    approved_weeks(
        owner_api, tenant, setup, [("2026-11-02", "2026-11-08"), ("2026-11-09", "2026-11-15")]
    )
    approved_vacation(tenant, setup["worker"], date(2026, 12, 1), date(2026, 12, 5), 5, "separate")
    base = {
        "run_type": "vacation",
        "scope": "company",
        "period_start": "2026-11-23",
        "period_end": "2026-12-06",
        "pay_date": "2026-11-27",
    }
    rid, calc = run(owner_api, **base)
    vac = items(owner_api, rid)["E-1"]["VACACIONES"]
    # Salario actual: 5 × 48 / 6 = 40/día; el promedio de 480 en 330 días es menor.
    assert (vac["amount"], calc["employee_count"]) == ("200.00", 1)
    assert "salario actual" in vac["detail"]

    owner_api.post(reverse("payroll-run-cancel", args=[rid]))
    with tenant_context(tenant):
        LegalParameter.objects.create(
            country="PA",
            key="vacation_pay_higher_of_current",
            name="x",
            value=D("0"),
            valid_from=date(2026, 11, 1),
        )
    rid, _ = run(owner_api, **base)
    vac = items(owner_api, rid)["E-1"]["VACACIONES"]
    assert vac["amount"] == "7.27"  # 5 × (480 / 330 días)
    assert "promedio" in vac["detail"]


def test_decimo_run(owner_api, tenant, setup):
    approved_weeks(
        owner_api, tenant, setup, [("2026-11-02", "2026-11-08"), ("2026-11-09", "2026-11-15")]
    )
    bad = owner_api.post(
        reverse("payroll-run-list"),
        {
            "run_type": "decimo",
            "scope": "company",
            "period_start": "2026-09-01",
            "period_end": "2026-12-15",
            "pay_date": "2026-12-15",
        },
        format="json",
    )
    assert bad.status_code == 400
    rid, calc = run(
        owner_api,
        run_type="decimo",
        scope="company",
        period_start="2026-08-16",
        period_end="2026-12-15",
        pay_date="2026-12-15",
    )
    assert calc["employee_count"] == 1  # el asalariado no tiene planillas aprobadas: se omite
    assert "sin salario devengado" in calc["notes"]
    got = items(owner_api, rid)["E-1"]
    assert got["DECIMO"]["amount"] == "40.00"  # (240 + 240) / 12
    assert got["DECIMO"]["cost_center_code"] == "P-1"
    assert got["CSS_DECIMO"]["amount"] == "2.90"  # 7.25 %
    assert got["CSS_DECIMO_PATRONAL"]["amount"] == "4.30"  # 10.75 %
    assert "SE" not in got and "CSS" not in got
    assert calc["net"] == "37.10"
