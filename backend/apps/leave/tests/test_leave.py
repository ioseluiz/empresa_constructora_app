from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.core.tenancy import tenant_context
from apps.hr.models import ProjectAssignment
from apps.hr.services import create_employee
from apps.iam.services import set_member_assignments
from apps.leave.models import VacationAdjustment, VacationRequest
from apps.leave.services import balance
from apps.organization.services import bootstrap_organization
from apps.projects.services import create_project
from apps.tenants.models import Membership
from apps.timeclock.models import WorkDay
from apps.timeclock.services import bootstrap_timeclock
from conftest import client_for, make_member

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup(tenant):
    bootstrap_organization(tenant, years=(2026,))
    with tenant_context(tenant):
        bootstrap_timeclock()
        p1 = create_project(code="P-1", name="Torre", status="active")
        p2 = create_project(code="P-2", name="Puente", status="active")
        ana = create_employee(
            code="E-1",
            first_name="Ana",
            last_name="Ruiz",
            id_number="8-1-1",
            hire_date=date(2026, 1, 5),
            payment_method="cash",
        )
        beto = create_employee(
            code="E-2",
            first_name="Beto",
            last_name="Sanz",
            id_number="8-2-2",
            hire_date=date(2026, 1, 5),
            payment_method="cash",
        )
        ProjectAssignment.objects.create(employee=ana, project=p1, start_date=date(2026, 1, 5))
        ProjectAssignment.objects.create(employee=beto, project=p2, start_date=date(2026, 1, 5))
    return {"ana": ana, "beto": beto, "p1": p1}


def test_balance_accrues_one_day_per_eleven(tenant, setup):
    with tenant_context(tenant):
        b = balance(setup["ana"], date(2026, 11, 30))  # 330 días desde el ingreso
        assert (b.earned, b.available) == (Decimal("30.00"), Decimal("30.00"))
        VacationAdjustment.objects.create(
            employee=setup["ana"], date=date(2026, 2, 1), days=Decimal("-5"), reason="Pagadas antes"
        )
        VacationRequest.objects.create(
            employee=setup["ana"],
            start_date=date(2026, 12, 7),
            end_date=date(2026, 12, 16),
            days=10,
            status="approved",
        )
        b = balance(setup["ana"], date(2026, 11, 30))
        assert (b.scheduled, b.adjustments, b.available) == (10, Decimal("-5"), Decimal("15.00"))


def request(api, employee, start="2026-12-07", days=10, mode="payroll"):
    return api.post(
        reverse("vacation-list"),
        {"employee": str(employee.pk), "start_date": start, "days": days, "payment_mode": mode},
        format="json",
    )


def test_request_approve_reject_cancel(owner_api, tenant, setup):
    created = request(owner_api, setup["ana"])
    assert created.status_code == 201, created.json()
    assert created.json()["end_date"] == "2026-12-16"
    assert request(owner_api, setup["ana"], start="2026-12-10").status_code == 400  # se cruza

    too_many = request(owner_api, setup["beto"], days=40).json()
    blocked = owner_api.post(reverse("vacation-approve", args=[too_many["id"]]), {}, format="json")
    assert blocked.status_code == 400 and "saldo" in blocked.json()["detail"]
    no_reason = owner_api.post(reverse("vacation-reject", args=[too_many["id"]]), {}, format="json")
    assert no_reason.status_code == 400
    rejected = owner_api.post(
        reverse("vacation-reject", args=[too_many["id"]]),
        {"reason": "Excede el saldo"},
        format="json",
    )
    assert rejected.json()["status"] == "rejected"

    approved = owner_api.post(
        reverse("vacation-approve", args=[created.json()["id"]]), {}, format="json"
    )
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    cancelled = owner_api.post(
        reverse("vacation-cancel", args=[created.json()["id"]]), {}, format="json"
    )
    assert cancelled.json()["status"] == "cancelled"

    balances = owner_api.get(reverse("vacation-balance-list")).json()["results"]
    assert {b["employee_code"] for b in balances} == {"E-1", "E-2"}


def test_vacation_days_are_not_absences(owner_api, tenant, setup):
    created = request(owner_api, setup["ana"], start="2026-11-16", days=3).json()
    owner_api.post(reverse("vacation-approve", args=[created["id"]]), {}, format="json")
    owner_api.post(
        reverse("workday-calculate"),
        {"date_from": "2026-11-16", "date_to": "2026-11-20"},
        format="json",
    )
    with tenant_context(tenant):
        absent = set(
            WorkDay.objects.filter(employee=setup["ana"], issues__contains=["absent"]).values_list(
                "date", flat=True
            )
        )
    assert absent == {date(2026, 11, 19), date(2026, 11, 20)}


def test_project_manager_scope(tenant, roles, setup, owner_api):
    user = make_member(tenant, "jefe@obra.pa", [], roles)
    m = Membership.objects.get(user=user)
    with tenant_context(tenant):
        set_member_assignments(m, [(roles["Jefe de proyecto"], [setup["p1"]])])
    jefe = client_for(user, tenant)
    own = request(owner_api, setup["ana"]).json()
    other = request(owner_api, setup["beto"]).json()
    rows = jefe.get(reverse("vacation-list")).json()["results"]
    assert [r["employee_code"] for r in rows] == ["E-1"]
    assert (
        jefe.post(reverse("vacation-approve", args=[own["id"]]), {}, format="json").status_code
        == 200
    )
    assert (
        jefe.post(reverse("vacation-approve", args=[other["id"]]), {}, format="json").status_code
        == 404
    )
    assert request(jefe, setup["ana"]).status_code == 403  # sin leave.manage
