from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db.models import Q, Sum
from django.utils import timezone

from apps.hr.models import Employee

from .models import VacationAdjustment, VacationRequest

DAYS_PER_VACATION_DAY = 11  # 30 días por cada 11 meses ≈ 1 día por cada 11 días
TWO = Decimal("0.01")


@dataclass
class Balance:
    earned: Decimal
    taken: int
    scheduled: int
    adjustments: Decimal
    available: Decimal
    pending_requests: int


def balance(employee: Employee, as_of: date | None = None) -> Balance:
    """Saldo de vacaciones a una fecha. `taken` son las ya iniciadas; `scheduled`, las
    aprobadas que empiezan después: ambas se descuentan del disponible."""
    as_of = as_of or timezone.localdate()
    end = min(as_of, employee.termination_date or as_of)
    worked_days = max(0, (end - employee.hire_date).days + 1)
    earned = (Decimal(worked_days) / DAYS_PER_VACATION_DAY).quantize(TWO, rounding=ROUND_HALF_UP)
    approved = VacationRequest.objects.filter(
        employee=employee, status=VacationRequest.Status.APPROVED
    )
    taken = approved.filter(start_date__lte=as_of).aggregate(t=Sum("days"))["t"] or 0
    scheduled = approved.filter(start_date__gt=as_of).aggregate(t=Sum("days"))["t"] or 0
    adjustments = VacationAdjustment.objects.filter(employee=employee, date__lte=as_of).aggregate(
        t=Sum("days")
    )["t"] or Decimal("0")
    pending = VacationRequest.objects.filter(
        employee=employee, status=VacationRequest.Status.REQUESTED
    ).count()
    return Balance(
        earned=earned,
        taken=taken,
        scheduled=scheduled,
        adjustments=adjustments,
        available=earned + adjustments - taken - scheduled,
        pending_requests=pending,
    )


def overlapping_requests(employee: Employee, start: date, end: date, exclude: Any = None) -> bool:
    qs = VacationRequest.objects.filter(
        employee=employee,
        status__in=[VacationRequest.Status.REQUESTED, VacationRequest.Status.APPROVED],
        start_date__lte=end,
        end_date__gte=start,
    )
    if exclude is not None:
        qs = qs.exclude(pk=exclude)
    return qs.exists()


def vacation_days_between(employee_id: Any, start: date, end: date) -> set[date]:
    """Días de vacaciones aprobadas del empleado dentro del rango."""
    days: set[date] = set()
    for v in VacationRequest.objects.filter(
        Q(start_date__lte=end) & Q(end_date__gte=start),
        employee_id=employee_id,
        status=VacationRequest.Status.APPROVED,
    ):
        d = max(v.start_date, start)
        while d <= min(v.end_date, end):
            days.add(d)
            d += timedelta(days=1)
    return days
