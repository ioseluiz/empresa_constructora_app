from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse

from apps.attendance.models import TimeEntry
from apps.core.tenancy import tenant_context
from apps.hr.models import ProjectAssignment
from apps.hr.services import create_employee
from apps.iam.services import set_member_assignments
from apps.organization.models import Holiday
from apps.organization.services import bootstrap_organization
from apps.projects.services import create_project
from apps.tenants.models import Membership
from apps.timeclock.models import Punch, Shift, ShiftAssignment, WorkDay
from apps.timeclock.services import bootstrap_timeclock
from conftest import client_for, make_member

pytestmark = pytest.mark.django_db
PA = ZoneInfo("America/Panama")
MON, TUE, WED = date(2026, 11, 16), date(2026, 11, 17), date(2026, 11, 18)


def at(day, hh, mm=0):
    return datetime.combine(day, time(hh, mm), PA)


@pytest.fixture
def setup(tenant):
    bootstrap_organization(tenant, years=(2026,))
    with tenant_context(tenant):
        bootstrap_timeclock()
        p1 = create_project(code="P-1", name="Torre", status="active")
        p2 = create_project(code="P-2", name="Puente", status="active")
        e1 = create_employee(
            code="E-1",
            first_name="Ana",
            last_name="Ruiz",
            id_number="8-1-1",
            hire_date=date(2026, 1, 5),
            payment_method="cash",
        )
        e2 = create_employee(
            code="E-2",
            first_name="Beto",
            last_name="Sanz",
            id_number="8-2-2",
            hire_date=date(2026, 1, 5),
            payment_method="cash",
        )
        ProjectAssignment.objects.create(employee=e1, project=p1, start_date=date(2026, 1, 5))
        ProjectAssignment.objects.create(employee=e2, project=p2, start_date=date(2026, 1, 5))
        for day in (MON, TUE):
            Punch.objects.create(
                employee=e1, timestamp=at(day, 7), direction="in", source="device", project=p1
            )
        Punch.objects.create(
            employee=e1, timestamp=at(MON, 18, 30), direction="out", source="device", project=p1
        )
        # El martes no marcó la salida; el miércoles no vino.
    return {"p1": p1, "p2": p2, "e1": e1, "e2": e2}


def calculate(api, **extra):
    return api.post(
        reverse("workday-calculate"),
        {"date_from": MON.isoformat(), "date_to": WED.isoformat(), **extra},
        format="json",
    )


def test_calculate_classifies_and_detects_issues(owner_api, tenant, setup):
    response = calculate(owner_api)
    assert response.status_code == 200, response.json()
    with tenant_context(tenant):
        days = {(w.employee.code, w.date): w for w in WorkDay.objects.select_related("employee")}
    mon = days[("E-1", MON)]
    assert mon.project == setup["p1"] and mon.status == "pending"
    assert (mon.ordinary_minutes, mon.overtime_day_minutes, mon.overtime_mixed_minutes) == (
        480,
        120,
        30,
    )
    assert days[("E-1", TUE)].issues == ["missing_out"]
    assert days[("E-1", WED)].issues == ["absent"]
    # E-2 no marcó en toda la semana: tres ausencias en su proyecto.
    assert [days[("E-2", d)].project for d in (MON, TUE, WED)] == [setup["p2"]] * 3

    summary = owner_api.get(
        reverse("workday-summary"), {"date_from": MON.isoformat(), "date_to": WED.isoformat()}
    ).json()
    assert summary["total"] == 6 and summary["review"] == 5 and summary["overtime_minutes"] == 150


def test_holiday_and_rest_day(owner_api, tenant, setup):
    with tenant_context(tenant):
        Holiday.objects.update_or_create(date=MON, defaults={"name": "Feriado prueba"})
        sunday = date(2026, 11, 15)
        Punch.objects.create(
            employee=setup["e2"],
            timestamp=at(sunday, 8),
            direction="in",
            source="manual",
            reason="x",
        )
        Punch.objects.create(
            employee=setup["e2"],
            timestamp=at(sunday, 12),
            direction="out",
            source="manual",
            reason="x",
        )
    owner_api.post(
        reverse("workday-calculate"),
        {"date_from": "2026-11-15", "date_to": MON.isoformat()},
        format="json",
    )
    with tenant_context(tenant):
        assert WorkDay.objects.get(employee=setup["e1"], date=MON).day_kind == "holiday"
        sun = WorkDay.objects.get(employee=setup["e2"], date=sunday)
        assert sun.day_kind == "rest" and sun.ordinary_minutes == 240
        # En el feriado no se genera ausencia para quien no marcó.
        assert not WorkDay.objects.filter(employee=setup["e2"], date=MON).exists()


def test_approve_generates_time_entries_and_reopen_removes_them(owner_api, tenant, setup):
    calculate(owner_api)
    with tenant_context(tenant):
        mon = WorkDay.objects.get(employee=setup["e1"], date=MON)
        tue = WorkDay.objects.get(employee=setup["e1"], date=TUE)
    blocked = owner_api.post(reverse("workday-approve"), {"ids": [str(tue.pk)]}, format="json")
    assert blocked.status_code == 400 and "incompletas" in blocked.json()["detail"]

    ok = owner_api.post(reverse("workday-approve"), {"ids": [str(mon.pk)]}, format="json")
    assert ok.status_code == 200, ok.json()
    with tenant_context(tenant):
        entries = {e.hour_type: e for e in TimeEntry.objects.filter(workday=mon)}
        assert entries["ordinary"].hours == Decimal("8.00")
        assert entries["ot_day"].hours == Decimal("2.00")
        assert entries["ot_mixed"].hours == Decimal("0.50")
        assert entries["ordinary"].cost_center == setup["p1"].cost_center

    # Recalcular no toca las aprobadas.
    calculate(owner_api)
    with tenant_context(tenant):
        assert WorkDay.objects.get(pk=mon.pk).status == "approved"
        assert TimeEntry.objects.filter(workday_id=mon.pk).count() == 3

    reopened = owner_api.post(reverse("workday-reopen", args=[mon.pk]))
    assert reopened.json()["status"] == "pending"
    with tenant_context(tenant):
        assert not TimeEntry.objects.filter(workday_id=mon.pk).exists()


def test_correcting_punch_recalculates_automatically(owner_api, tenant, setup):
    calculate(owner_api)
    response = owner_api.post(
        reverse("punch-manual"),
        {
            "employees": [str(setup["e1"].pk)],
            "date": TUE.isoformat(),
            "time": "16:00",
            "direction": "out",
            "project": str(setup["p1"].pk),
            "reason": "Olvidó marcar la salida",
        },
        format="json",
    )
    assert response.status_code == 201, response.json()
    with tenant_context(tenant):
        tue = WorkDay.objects.get(employee=setup["e1"], date=TUE)
        assert tue.issues == [] and tue.ordinary_minutes == 480


def test_shift_assignment_bulk_closes_previous(owner_api, tenant, setup):
    with tenant_context(tenant):
        night = Shift.objects.create(
            code="NOC", name="Nocturno", start_time=time(22), end_time=time(6)
        )
        default = Shift.objects.get(is_default=True)
        ShiftAssignment.objects.create(
            employee=setup["e1"], shift=default, start_date=date(2026, 1, 5)
        )
    response = owner_api.post(
        reverse("shift-assignment-bulk"),
        {
            "shift": str(night.pk),
            "employees": [str(setup["e1"].pk), str(setup["e2"].pk)],
            "start_date": "2026-12-01",
        },
        format="json",
    )
    assert response.json() == {"assigned": 2, "skipped": []}
    with tenant_context(tenant):
        previous = ShiftAssignment.objects.get(employee=setup["e1"], shift=default)
        assert previous.end_date == date(2026, 11, 30)


def test_only_one_default_shift(owner_api, tenant, setup):
    response = owner_api.post(
        reverse("shift-list"),
        {
            "code": "sab",
            "name": "Sábado",
            "start_time": "07:00",
            "end_time": "11:00",
            "workdays": [5],
            "is_default": True,
        },
        format="json",
    )
    assert response.status_code == 201, response.json()
    with tenant_context(tenant):
        assert list(Shift.objects.filter(is_default=True).values_list("code", flat=True)) == ["SAB"]


class TestScope:
    def member(self, tenant, roles, role_name, project):
        user = make_member(tenant, f"{role_name[:4].lower()}@obra.pa", [], roles)
        m = Membership.objects.get(user=user)
        with tenant_context(tenant):
            set_member_assignments(m, [(roles[role_name], [project])])
        return client_for(user, tenant)

    def test_project_manager_approves_only_own_project(self, owner_api, tenant, roles, setup):
        calculate(owner_api)
        jefe = self.member(tenant, roles, "Jefe de proyecto", setup["p1"])
        rows = jefe.get(reverse("workday-list"), {"date_from": MON.isoformat()}).json()["results"]
        assert {r["project_code"] for r in rows} == {"P-1"}
        with tenant_context(tenant):
            own = WorkDay.objects.get(employee=setup["e1"], date=MON)
            other = WorkDay.objects.get(employee=setup["e2"], date=MON)
        assert (
            jefe.post(reverse("workday-approve"), {"ids": [str(own.pk)]}, format="json").status_code
            == 200
        )
        assert (
            jefe.post(
                reverse("workday-approve"), {"ids": [str(other.pk)]}, format="json"
            ).status_code
            == 400
        )

    def test_supervisor_can_calculate_own_project_but_not_approve(self, tenant, roles, setup):
        sup = self.member(tenant, roles, "Supervisor de obra", setup["p1"])
        assert calculate(sup).status_code == 403  # toda la empresa
        assert calculate(sup, project=str(setup["p1"].pk)).status_code == 200
        with tenant_context(tenant):
            assert set(WorkDay.objects.values_list("employee__code", flat=True)) == {"E-1"}
            wid = WorkDay.objects.filter(status="pending").values_list("pk", flat=True).first()
        assert (
            sup.post(reverse("workday-approve"), {"ids": [str(wid)]}, format="json").status_code
            == 403
        )


def test_new_tenant_gets_default_shift(db):
    from apps.tenants.services import create_tenant
    from conftest import PASSWORD

    new, _ = create_tenant(name="Obra Nueva", owner_email="n@o.pa", owner_password=PASSWORD)
    with tenant_context(new):
        shift = Shift.objects.get(is_default=True)
        assert (shift.start_time, shift.end_time, shift.paid_minutes) == (time(7), time(16), 480)


def test_time_entries_endpoint(owner_api, tenant, setup):
    calculate(owner_api)
    with tenant_context(tenant):
        mon = WorkDay.objects.get(employee=setup["e1"], date=MON)
    owner_api.post(reverse("workday-approve"), {"ids": [str(mon.pk)]}, format="json")
    rows = owner_api.get(reverse("time-entry-list"), {"project": str(setup["p1"].pk)}).json()
    assert sorted(r["hour_type"] for r in rows["results"]) == ["ordinary", "ot_day", "ot_mixed"]


def test_today_is_not_marked_absent(owner_api, tenant, setup, monkeypatch):
    from django.utils import timezone

    monkeypatch.setattr(timezone, "localdate", lambda *a, **k: WED)
    calculate(owner_api)
    with tenant_context(tenant):
        assert not WorkDay.objects.filter(employee=setup["e1"], date=WED).exists()
        assert WorkDay.objects.get(employee=setup["e2"], date=TUE).issues == ["absent"]
