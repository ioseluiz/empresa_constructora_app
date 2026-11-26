"""Pago de vacaciones: salario diario = promedio de lo devengado en los últimos 11 meses, o el
salario actual si es mayor (parámetro `vacation_pay_higher_of_current`). ⚠️ Validar con
asesoría laboral."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db.models import Sum

from apps.hr.models import Employee, EmploymentContract

from .models import PayrollLineItem, PayrollRun
from .params import Parameters

FOUR = Decimal("0.0001")


@dataclass
class VacationPay:
    request_id: Any
    days: int
    daily_rate: Decimal
    amount: Decimal
    detail: str


def current_daily_salary(contract: EmploymentContract, on: date) -> Decimal:
    record = contract.salary_on(on)
    if record is None:
        return Decimal("0")
    amount = record.amount
    if record.uses_cba_rate and contract.cba_category is not None:
        rate = contract.cba_category.rate_on(on)
        amount = rate.hourly_rate if rate else None
    if amount is None:
        return Decimal("0")
    if contract.pay_basis == EmploymentContract.PayBasis.MONTHLY:
        return (amount / 30).quantize(FOUR, rounding=ROUND_HALF_UP)
    # Por hora: jornada diaria promedio de una semana de 6 días.
    return (amount * (contract.weekly_hours or Decimal("48")) / 6).quantize(
        FOUR, rounding=ROUND_HALF_UP
    )


def average_daily_earnings(
    employee: Employee, before: date, months: int
) -> tuple[Decimal, int, Decimal]:
    """(promedio diario, días de la ventana, total devengado) de las planillas aprobadas."""
    window_start = max(before - timedelta(days=months * 30), employee.hire_date)
    days = (before - window_start).days
    total = PayrollLineItem.objects.filter(
        line__employee=employee,
        line__run__status__in=[PayrollRun.Status.APPROVED, PayrollRun.Status.PAID],
        line__run__period_end__gte=window_start,
        line__run__period_end__lt=before,
        kind="earning",
        concept__taxable_css=True,
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    if days <= 0:
        return Decimal("0"), 0, total
    return (total / days).quantize(FOUR, rounding=ROUND_HALF_UP), days, total


def vacation_pay(
    employee: Employee, contract: EmploymentContract, request: Any, params: Parameters
) -> VacationPay:
    months = int(params.rate("vacation_average_months"))
    average, days, total = average_daily_earnings(employee, request.start_date, months)
    current = current_daily_salary(contract, request.start_date)
    use_current = params.rate("vacation_pay_higher_of_current") >= 1 and current > average
    if average <= 0:
        use_current = True
    daily = current if use_current else average
    detail = (
        f"{request.days} días × {daily} (salario actual)"
        if use_current
        else f"{request.days} días × {daily} (promedio de {total} en {days} días)"
    )
    amount = (daily * request.days).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return VacationPay(request.pk, request.days, daily, amount, detail)
