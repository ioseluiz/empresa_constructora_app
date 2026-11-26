from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.attendance.models import TimeEntry
from apps.core.tenancy import tenant_context
from apps.hr.models import ProjectAssignment
from apps.hr.services import create_contract, create_employee
from apps.iam.services import set_member_assignments
from apps.organization.models import Position
from apps.organization.services import bootstrap_organization
from apps.payroll import runs
from apps.payroll.models import PayrollConcept, PayrollLine, PayrollRun, RecurringDeduction
from apps.payroll.services import bootstrap_payroll
from apps.projects.services import create_project
from apps.tenants.models import Membership
from apps.timeclock.models import WorkDay
from apps.timeclock.services import bootstrap_timeclock
from conftest import client_for, make_member

pytestmark = pytest.mark.django_db
D = Decimal
WEEK = {"period_start": "2026-11-16", "period_end": "2026-11-22", "pay_date": "2026-11-27"}


def add_hours(employee, project, day, hours="8"):
    wd = WorkDay.objects.create(
        employee=employee, date=day, project=project, day_kind="regular", status="approved"
    )
    return TimeEntry.objects.create(
        employee=employee,
        date=day,
        project=project,
        cost_center=project.cost_center,
        hour_type="ordinary",
        day_kind="regular",
        hours=D(hours),
        workday=wd,
    )


@pytest.fixture
def setup(tenant):
    bootstrap_organization(tenant, years=(2026,))
    with tenant_context(tenant):
        bootstrap_timeclock()
        bootstrap_payroll()
        p1 = create_project(code="P-1", name="Torre", status="active")
        p2 = create_project(code="P-2", name="Puente", status="active")
        alb = Position.objects.get(code="ALB")

        def worker(code, cedula, project, rate):
            e = create_employee(
                code=code,
                first_name=code,
                last_name="Obra",
                id_number=cedula,
                hire_date=date(2026, 1, 5),
                payment_method="cash",
            )
            ProjectAssignment.objects.create(
                employee=e, project=project, start_date=date(2026, 1, 5)
            )
            create_contract(
                employee=e,
                contract_type="project",
                start_date=date(2026, 1, 5),
                position=alb,
                project=project,
                pay_frequency="weekly",
                pay_basis="hourly",
                initial_amount=D(rate),
                uses_cba_rate=False,
            )
            return e

        w1, w2 = worker("E-1", "8-1-1", p1, "5"), worker("E-2", "8-2-2", p2, "4")
        clerk = create_employee(
            code="E-3",
            first_name="Ofi",
            last_name="Cina",
            id_number="8-3-3",
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
        for day in (date(2026, 11, 16), date(2026, 11, 17)):
            add_hours(w1, p1, day)
            add_hours(w2, p2, day)
        loan = RecurringDeduction.objects.create(
            employee=w1,
            concept=PayrollConcept.objects.get(code="PRESTAMO"),
            amount_per_period=D("10"),
            total_amount=D("15"),
            start_date=date(2026, 11, 1),
        )
    return {"p1": p1, "p2": p2, "w1": w1, "w2": w2, "clerk": clerk, "loan": loan}


def create(api, **extra):
    return api.post(
        reverse("payroll-run-list"), {**WEEK, "frequency": "weekly", **extra}, format="json"
    )


def act(api, run_id, name):
    return api.post(reverse(f"payroll-run-{name}", args=[run_id]))


def test_project_run_full_cycle(owner_api, tenant, setup):
    response = create(owner_api, scope="project", project=str(setup["p1"].pk))
    assert response.status_code == 201, response.json()
    run = response.json()
    assert run["number"] == 1 and run["status"] == "draft"

    calculated = act(owner_api, run["id"], "calculate").json()
    assert calculated["status"] == "calculated" and calculated["employee_count"] == 1
    assert calculated["gross"] == "80.00"  # 16 h × 5.00
    lines = owner_api.get(reverse("payroll-run-lines", args=[run["id"]])).json()["results"]
    assert [ln["employee_code"] for ln in lines] == ["E-1"]
    codes = {i["code"]: i for i in lines[0]["items"]}
    assert codes["PRESTAMO"]["amount"] == "10.00"
    assert codes["CSS_PATRONAL"]["cost_center_code"] == "P-1"

    approved = act(owner_api, run["id"], "approve").json()
    assert approved["status"] == "approved"
    with tenant_context(tenant):
        assert TimeEntry.objects.filter(employee=setup["w1"], locked=True).count() == 2
        setup["loan"].refresh_from_db()
        assert setup["loan"].paid_amount == D("10.00") and setup["loan"].is_active

    # Inmutable: no se recalcula ni se anula; sí se marca como pagada.
    assert act(owner_api, run["id"], "calculate").status_code == 400
    assert act(owner_api, run["id"], "cancel").status_code == 400
    assert act(owner_api, run["id"], "pay").json()["status"] == "paid"


def test_next_week_pays_late_approved_hours_and_finishes_loan(owner_api, tenant, setup):
    first = create(owner_api, scope="project", project=str(setup["p1"].pk)).json()
    act(owner_api, first["id"], "calculate")
    act(owner_api, first["id"], "approve")
    with tenant_context(tenant):
        add_hours(setup["w1"], setup["p1"], date(2026, 11, 18), "4")  # aprobada tarde
        add_hours(setup["w1"], setup["p1"], date(2026, 11, 23), "8")
    second = create(
        owner_api,
        scope="project",
        project=str(setup["p1"].pk),
        period_start="2026-11-23",
        period_end="2026-11-29",
        pay_date="2026-12-04",
    ).json()
    result = act(owner_api, second["id"], "calculate").json()
    assert result["gross"] == "60.00"  # 12 h × 5.00 (incluye las 4 h del 18/11)
    lines = owner_api.get(reverse("payroll-run-lines", args=[second["id"]])).json()["results"]
    assert {i["code"]: i["amount"] for i in lines[0]["items"]}["PRESTAMO"] == "5.00"  # saldo
    assert any("anteriores" in x for x in lines[0]["explanation"])
    act(owner_api, second["id"], "approve")
    with tenant_context(tenant):
        setup["loan"].refresh_from_db()
        assert setup["loan"].paid_amount == D("15.00") and not setup["loan"].is_active


def test_scopes_and_no_double_pay(owner_api, tenant, setup):
    company = create(owner_api, scope="company").json()
    act(owner_api, company["id"], "calculate")
    project = create(owner_api, scope="project", project=str(setup["p1"].pk)).json()
    result = act(owner_api, project["id"], "calculate").json()
    assert result["employee_count"] == 0
    assert "ya está en la planilla #1" in result["notes"]

    act(owner_api, company["id"], "cancel")
    assert act(owner_api, project["id"], "calculate").json()["employee_count"] == 1

    office = create(
        owner_api,
        scope="office",
        frequency="biweekly",
        period_start="2026-11-16",
        period_end="2026-11-30",
        pay_date="2026-11-30",
    ).json()
    office_result = act(owner_api, office["id"], "calculate").json()
    assert office_result["employee_count"] == 1 and office_result["gross"] == "600.00"


def test_approval_blocked_by_errors_and_paid_hours(owner_api, tenant, setup, monkeypatch):
    run = create(owner_api, scope="project", project=str(setup["p2"].pk)).json()
    original = runs.calculate

    def failing(employee, *args, **kwargs):
        raise runs.PayrollInputError("Sin salario registrado")

    monkeypatch.setattr(runs, "calculate", failing)
    act(owner_api, run["id"], "calculate")
    blocked = act(owner_api, run["id"], "approve")
    assert blocked.status_code == 400 and "error" in blocked.json()["detail"]
    monkeypatch.setattr(runs, "calculate", original)

    # Dos borradores con las mismas horas: aprobar el segundo exige recalcular.
    act(owner_api, run["id"], "calculate")
    with tenant_context(tenant):
        other = runs.create_run(
            frequency="weekly",
            scope="project",
            project=setup["p2"],
            period_start=date(2026, 11, 16),
            period_end=date(2026, 11, 22),
            pay_date=date(2026, 11, 27),
        )
        line = PayrollLine.objects.get(run_id=run["id"])
        PayrollLine.objects.create(
            run=other, employee=line.employee, time_entry_ids=line.time_entry_ids
        )
        other.status = PayrollRun.Status.CALCULATED
        other.save()
    assert act(owner_api, run["id"], "approve").status_code == 200
    again = act(owner_api, str(other.pk), "approve")
    assert again.status_code == 400 and "recalcula" in again.json()["detail"]


def test_consolidated_global_payroll(owner_api, tenant, setup):
    for project in ("p1", "p2"):
        run = create(owner_api, scope="project", project=str(setup[project].pk)).json()
        act(owner_api, run["id"], "calculate")
        act(owner_api, run["id"], "approve")
    response = owner_api.get(
        reverse("payroll-consolidated"), {"date_from": "2026-11-01", "date_to": "2026-11-30"}
    )
    body = response.json()
    assert body["runs"] == 2 and body["employees"] == 2
    assert body["totals"]["gross"] == "144.00"  # 80 + 64
    by_cc = {row["cost_center"]: row for row in body["by_cost_center"]}
    assert by_cc["P-1"]["earning"] == "80.00" and by_cc["P-2"]["earning"] == "64.00"
    assert D(by_cc["P-1"]["total_cost"]) > D("80.00")
    assert any(c["code"] == "CSS" for c in body["by_concept"])


def test_project_scoped_payroll_clerk(tenant, roles, setup, owner_api):
    user = make_member(tenant, "pl@obra.pa", [], roles)
    m = Membership.objects.get(user=user)
    with tenant_context(tenant):
        set_member_assignments(m, [(roles["Planillero"], [setup["p1"]])])
    api = client_for(user, tenant)
    assert create(api, scope="company").status_code == 403
    assert create(api, scope="project", project=str(setup["p2"].pk)).status_code == 403
    own = create(api, scope="project", project=str(setup["p1"].pk))
    assert own.status_code == 201
    create(owner_api, scope="project", project=str(setup["p2"].pk))
    visible = api.get(reverse("payroll-run-list")).json()["results"]
    assert [r["project_code"] for r in visible] == ["P-1"]
    act(api, own.json()["id"], "calculate")
    assert act(api, own.json()["id"], "approve").status_code == 403  # sin payroll.approve
    assert (
        api.get(
            reverse("payroll-consolidated"), {"date_from": "2026-11-01", "date_to": "2026-11-30"}
        ).status_code
        == 403
    )
