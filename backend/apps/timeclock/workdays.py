"""Cálculo, aprobación y reapertura de jornadas (`WorkDay`) a partir de las marcaciones."""

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.attendance.models import TimeEntry
from apps.core.tenancy import require_current_tenant
from apps.hr.models import Employee, ProjectAssignment
from apps.leave.services import vacation_days_between
from apps.organization.models import CostCenter, Holiday
from apps.organization.services import HEAD_OFFICE_CODE

from . import engine
from .models import Punch, Shift, ShiftAssignment, WorkDay

MAX_RANGE_DAYS = 62


def rule_for(shift: Shift) -> engine.ShiftRule:
    return engine.ShiftRule(
        start_time=shift.start_time,
        end_time=shift.end_time,
        break_minutes=shift.break_minutes,
        break_after_minutes=shift.break_after_minutes,
        workdays=tuple(shift.workdays),
        late_tolerance_minutes=shift.late_tolerance_minutes,
        overtime_rounding_minutes=shift.overtime_rounding_minutes,
        count_early_arrival=shift.count_early_arrival,
    )


class ShiftResolver:
    def __init__(self, employee_ids: Iterable[Any], date_from: date, date_to: date) -> None:
        self.default = Shift.objects.filter(is_default=True, is_active=True).first()
        self.by_employee: dict[Any, list[ShiftAssignment]] = defaultdict(list)
        qs = ShiftAssignment.objects.filter(
            Q(end_date__isnull=True) | Q(end_date__gte=date_from),
            employee_id__in=list(employee_ids),
            start_date__lte=date_to,
        ).select_related("shift")
        for a in qs:
            self.by_employee[a.employee_id].append(a)

    def on(self, employee_id: Any, day: date) -> Shift | None:
        for a in self.by_employee.get(employee_id, []):
            if a.start_date <= day and (a.end_date is None or a.end_date >= day):
                return a.shift
        return self.default


class AssignmentResolver:
    def __init__(self, employee_ids: Iterable[Any], date_from: date, date_to: date) -> None:
        self.by_employee: dict[Any, list[ProjectAssignment]] = defaultdict(list)
        qs = ProjectAssignment.objects.filter(
            Q(end_date__isnull=True) | Q(end_date__gte=date_from),
            employee_id__in=list(employee_ids),
            start_date__lte=date_to,
        )
        for a in qs:
            self.by_employee[a.employee_id].append(a)

    def projects_on(self, employee_id: Any, day: date) -> list[Any]:
        return [
            a.project_id
            for a in self.by_employee.get(employee_id, [])
            if a.start_date <= day and (a.end_date is None or a.end_date >= day)
        ]


def _employed_on(employee: Employee, day: date) -> bool:
    return employee.hire_date <= day and (
        employee.termination_date is None or day <= employee.termination_date
    )


@transaction.atomic
def calculate(employees: Iterable[Employee], date_from: date, date_to: date) -> dict[str, int]:
    """Recalcula las jornadas del rango. Las aprobadas no se tocan."""
    employees = list(employees)
    today = timezone.localdate()
    date_to = min(date_to, today)
    if not employees or date_from > date_to:
        return {"workdays": 0, "skipped_approved": 0}
    tenant = require_current_tenant()
    tz = ZoneInfo(tenant.timezone)
    ids = [e.pk for e in employees]
    shifts = ShiftResolver(ids, date_from, date_to)
    assignments = AssignmentResolver(ids, date_from, date_to)
    holidays = set(
        Holiday.objects.filter(
            date__gte=date_from, date__lte=date_to, is_paid_rest=True
        ).values_list("date", flat=True)
    )
    window_start = datetime.combine(date_from - timedelta(days=1), time(0), tz)
    window_end = datetime.combine(date_to + timedelta(days=2), time(0), tz)
    punches: dict[Any, list[engine.PunchData]] = defaultdict(list)
    for employee_id, ts, direction, project_id in Punch.objects.filter(
        is_void=False,
        employee_id__in=ids,
        timestamp__gte=window_start,
        timestamp__lt=window_end,
    ).values_list("employee_id", "timestamp", "direction", "project_id"):
        punches[employee_id].append(engine.PunchData(ts, direction, project_id))

    approved = set(
        WorkDay.objects.filter(
            employee_id__in=ids,
            date__gte=date_from,
            date__lte=date_to,
            status=WorkDay.Status.APPROVED,
        ).values_list("employee_id", "date")
    )
    WorkDay.objects.filter(employee_id__in=ids, date__gte=date_from, date__lte=date_to).exclude(
        status=WorkDay.Status.APPROVED
    ).delete()

    rows: list[WorkDay] = []
    for employee in employees:
        worked_dates: set[date] = set()
        for group in engine.cluster(punches.get(employee.pk, [])):
            day = group[0].timestamp.astimezone(tz).date()
            if not (date_from <= day <= date_to) or (employee.pk, day) in approved:
                continue
            shift = shifts.on(employee.pk, day)
            rule = rule_for(shift) if shift else None
            result = engine.evaluate(day, group, rule, engine.day_kind_for(day, rule, holidays), tz)
            assigned = assignments.projects_on(employee.pk, day)
            if result.project_id and result.project_id not in assigned:
                result.issues.append("unassigned_project")
            elif not result.project_id and len(assigned) == 1:
                result.project_id = assigned[0]
            if day in worked_dates:
                # Dos jornadas el mismo día (p. ej. turno partido de más de 6 h): se suman.
                _merge(rows, employee, result)
                continue
            worked_dates.add(day)
            rows.append(_to_model(tenant, employee, shift, result))

        on_vacation = vacation_days_between(employee.pk, date_from, date_to)
        day = date_from
        while day <= date_to:
            shift = shifts.on(employee.pk, day)
            if (
                shift is not None
                and day < today  # el día en curso aún no termina: no es ausencia
                and day not in worked_dates
                and day not in on_vacation
                and (employee.pk, day) not in approved
                and _employed_on(employee, day)
                and engine.day_kind_for(day, rule_for(shift), holidays) == "regular"
            ):
                result = engine.absence(day, rule_for(shift))
                assigned = assignments.projects_on(employee.pk, day)
                result.project_id = assigned[0] if len(assigned) == 1 else None
                rows.append(_to_model(tenant, employee, shift, result))
            day += timedelta(days=1)

    WorkDay.objects.bulk_create(rows, batch_size=1000)
    return {"workdays": len(rows), "skipped_approved": len(approved)}


def _to_model(tenant: Any, employee: Employee, shift: Shift | None, r: engine.DayResult) -> WorkDay:
    return WorkDay(
        tenant=tenant,
        employee=employee,
        date=r.date,
        project_id=r.project_id,
        shift=shift,
        day_kind=r.day_kind,
        jornada=r.jornada,
        first_in=r.first_in,
        last_out=r.last_out,
        segments=[[s.isoformat(), e.isoformat()] for s, e in r.segments],
        worked_minutes=r.worked_minutes,
        break_minutes=r.break_minutes,
        ordinary_minutes=r.ordinary_minutes,
        overtime_day_minutes=r.overtime_day_minutes,
        overtime_night_minutes=r.overtime_night_minutes,
        overtime_mixed_minutes=r.overtime_mixed_minutes,
        late_minutes=r.late_minutes,
        missing_minutes=r.missing_minutes,
        issues=sorted(set(r.issues)),
        status=WorkDay.Status.REVIEW if r.issues else WorkDay.Status.PENDING,
    )


def _merge(rows: list[WorkDay], employee: Employee, r: engine.DayResult) -> None:
    target = next(w for w in reversed(rows) if w.employee_id == employee.pk and w.date == r.date)
    for attr in (
        "worked_minutes",
        "break_minutes",
        "ordinary_minutes",
        "overtime_day_minutes",
        "overtime_night_minutes",
        "overtime_mixed_minutes",
    ):
        setattr(target, attr, getattr(target, attr) + getattr(r, attr))
    target.segments = [*target.segments, *[[s.isoformat(), e.isoformat()] for s, e in r.segments]]
    target.last_out = r.last_out or target.last_out
    target.issues = sorted({*target.issues, *r.issues})
    target.status = WorkDay.Status.REVIEW if target.issues else WorkDay.Status.PENDING


def recalculate_for(pairs: Iterable[tuple[Any, datetime]]) -> None:
    """Recalcula las jornadas afectadas por marcaciones nuevas, corregidas o anuladas."""
    tz = ZoneInfo(require_current_tenant().timezone)
    by_employee: dict[Any, list[date]] = defaultdict(list)
    for employee_id, ts in pairs:
        local = ts.astimezone(tz).date()
        by_employee[employee_id].extend([local - timedelta(days=1), local])
    for employee in Employee.objects.filter(pk__in=list(by_employee)):
        days = by_employee[employee.pk]
        calculate([employee], min(days), max(days))


HOUR_FIELDS = (
    (TimeEntry.HourType.ORDINARY, "ordinary_minutes"),
    (TimeEntry.HourType.OVERTIME_DAY, "overtime_day_minutes"),
    (TimeEntry.HourType.OVERTIME_NIGHT, "overtime_night_minutes"),
    (TimeEntry.HourType.OVERTIME_MIXED, "overtime_mixed_minutes"),
)


class ApprovalError(Exception):
    pass


def to_hours(mins: int) -> Decimal:
    return (Decimal(mins) / Decimal(60)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@transaction.atomic
def approve(workdays: Iterable[WorkDay], user: Any, notes: str = "") -> list[WorkDay]:
    workdays = list(workdays)
    blocked = [w for w in workdays if engine.BLOCKING_ISSUES & set(w.issues)]
    if blocked:
        raise ApprovalError(
            f"{len(blocked)} jornada(s) tienen marcaciones incompletas: "
            "corrígelas antes de aprobar."
        )
    head_office = CostCenter.objects.get(code=HEAD_OFFICE_CODE)
    now = timezone.now()
    entries = []
    for w in workdays:
        if w.status == WorkDay.Status.APPROVED:
            continue
        cost_center = w.project.cost_center if w.project is not None else head_office
        for hour_type, attr in HOUR_FIELDS:
            mins = getattr(w, attr)
            if mins > 0:
                entries.append(
                    TimeEntry(
                        tenant=w.tenant,
                        employee_id=w.employee_id,
                        date=w.date,
                        project_id=w.project_id,
                        cost_center=cost_center,
                        hour_type=hour_type,
                        day_kind=w.day_kind,
                        jornada=w.jornada,
                        hours=to_hours(mins),
                        workday=w,
                        created_by=user,
                    )
                )
        w.status, w.approved_at, w.approved_by = WorkDay.Status.APPROVED, now, user
        if notes:
            w.notes = notes[:255]
        w.save(update_fields=["status", "approved_at", "approved_by", "notes", "updated_at"])
    TimeEntry.objects.bulk_create(entries)
    return workdays


@transaction.atomic
def reopen(workday: WorkDay) -> WorkDay:
    if workday.time_entries.filter(locked=True).exists():
        raise ApprovalError("Las horas de esta jornada ya se usaron en una planilla.")
    workday.time_entries.all().delete()
    workday.status = WorkDay.Status.REVIEW if workday.issues else WorkDay.Status.PENDING
    workday.approved_at = workday.approved_by = None
    workday.save(update_fields=["status", "approved_at", "approved_by", "updated_at"])
    return workday
