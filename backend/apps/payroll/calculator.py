"""Prepara el `PayInput` de un empleado y período desde la base de datos y ejecuta las reglas
del país. No guarda nada: las corridas de planilla (Sprint 9) persisten el resultado."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Q

from apps.attendance.models import TimeEntry
from apps.hr.models import Employee, EmploymentContract, SalaryRecord
from apps.leave.services import vacation_days_between
from apps.organization.models import CBAWageRate
from apps.timeclock.models import WorkDay

from .engine import ZERO, DeductionInput, HoursEntry, PayInput, PayResult
from .models import PayrollSettings, RecurringDeduction
from .params import Parameters
from .rules import rules_for
from .services import settings_for_tenant
from .vacations import vacation_pay

FREQUENCY_FACTOR = {
    "weekly": Decimal(12) / Decimal(52),
    "biweekly": Decimal("0.5"),
    "monthly": Decimal("1"),
}


PRIOR_UNPAID_DAYS = 62


class PayrollInputError(Exception):
    pass


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


class RateBook:
    """Tarifas vigentes por fecha de un contrato (historial salarial y tabla de la convención)."""

    def __init__(self, contract: EmploymentContract) -> None:
        self.contract = contract
        self.salaries = list(contract.salary_history.order_by("valid_from"))
        self.cba = (
            list(CBAWageRate.objects.filter(category=contract.cba_category).order_by("valid_from"))
            if contract.cba_category_id
            else []
        )

    @staticmethod
    def _on(items: list[Any], day: date) -> Any:
        current = None
        for item in items:
            if item.valid_from <= day:
                current = item
        return current

    def salary(self, day: date) -> SalaryRecord | None:
        return self._on(self.salaries, day)

    def cba_rate(self, day: date) -> Decimal | None:
        rate = self._on(self.cba, day)
        return rate.hourly_rate if rate else None

    def amount(self, day: date) -> tuple[Decimal | None, str]:
        record = self.salary(day)
        if record is None:
            return None, "sin salario registrado"
        if record.uses_cba_rate:
            rate = self.cba_rate(day)
            return rate, "tarifa de convención" if rate else "sin tarifa de convención vigente"
        return record.amount, "salario del contrato"


def _add_vacations(
    inp: PayInput,
    employee: Employee,
    contract: EmploymentContract,
    end: date,
    mode: str,
    params: Parameters,
) -> None:
    from apps.leave.models import VacationRequest

    payment_mode = (
        VacationRequest.PaymentMode.SEPARATE
        if mode == "vacation"
        else VacationRequest.PaymentMode.PAYROLL
    )
    for request in VacationRequest.objects.filter(
        employee=employee,
        status=VacationRequest.Status.APPROVED,
        payment_mode=payment_mode,
        paid_line__isnull=True,
        start_date__lte=end,
    ).order_by("start_date"):
        inp.vacations.append(vacation_pay(employee, contract, request, params))


def build_input(
    employee: Employee,
    start: date,
    end: date,
    mode: str = "regular",
    params: Parameters | None = None,
) -> PayInput:
    """`mode`: "regular" (planilla regular, incluye vacaciones a pagar en ella) o "vacation"
    (solo las vacaciones aprobadas para pagarse en planilla de vacaciones)."""
    contracts = list(
        employee.contracts.exclude(status=EmploymentContract.Status.CANCELLED)
        .filter(start_date__lte=end)
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=start))
        .select_related("cost_center", "cba_category")
        .order_by("start_date")
    )
    if not contracts:
        raise PayrollInputError(f"{employee.full_name} no tiene contrato vigente en el período.")
    contract = contracts[-1]
    books = {c.pk: RateBook(c) for c in contracts}

    def contract_on(day: date) -> EmploymentContract | None:
        for c in contracts:
            if c.start_date <= day and (c.end_date is None or c.end_date >= day):
                return c
        return None

    inp = PayInput(
        contract_id=contract.pk,
        employee_id=employee.pk,
        period_start=start,
        period_end=end,
        pay_basis=contract.pay_basis,
        frequency=contract.pay_frequency,
        default_cost_center_id=contract.cost_center_id,
        union_member=employee.is_union_member,
    )
    days = _days(start, end)
    if mode == "vacation":
        if params is not None:
            _add_vacations(inp, employee, contract, end, mode, params)
        # El pago de vacaciones equivale a un mes de salario: el ISR se proyecta como mensual.
        inp.frequency = "monthly"
        return inp
    vacation_days = vacation_days_between(employee.pk, start, end)

    if contract.pay_basis == EmploymentContract.PayBasis.MONTHLY:
        factor = FREQUENCY_FACTOR[contract.pay_frequency] / len(days)
        total, paid_days = ZERO, 0
        for day in days:
            c = contract_on(day)
            if c is None or c.pay_basis != EmploymentContract.PayBasis.MONTHLY:
                continue
            if day in vacation_days:
                continue  # se pagan como vacaciones
            amount, _ = books[c.pk].amount(day)
            if amount is None:
                inp.warnings.append(f"Sin salario registrado el {day:%d/%m/%Y}.")
                continue
            total += amount * factor
            paid_days += 1
        inp.base_salary = total
        monthly_now, _ = books[contract.pk].amount(min(end, contract.end_date or end))
        weekly_hours = contract.weekly_hours or Decimal("48")
        inp.hourly_rate = ((monthly_now or ZERO) * 12 / (52 * weekly_hours)).quantize(
            Decimal("0.0001")
        )
        if vacation_days:
            inp.explanation.append(
                f"{len(vacation_days)} día(s) de vacaciones no se pagan como salario."
            )
        if paid_days < len(days):
            inp.explanation.append(f"Salario proporcional a {paid_days} de {len(days)} días.")
        inp.explanation.append(
            f"Valor hora {inp.hourly_rate} = salario mensual × 12 / (52 × {weekly_hours} h)."
        )

    # Horas aprobadas aún no pagadas: las del período y las aprobadas tarde de períodos
    # anteriores (hasta 62 días), que se pagan como ajuste en esta planilla.
    entries = TimeEntry.objects.filter(
        employee=employee,
        locked=False,
        date__gte=start - timedelta(days=PRIOR_UNPAID_DAYS),
        date__lte=end,
    ).order_by("date")
    prior = [e for e in entries if e.date < start]
    if prior:
        inp.explanation.append(
            f"Incluye {len(prior)} registro(s) de horas de días anteriores al período "
            "aún no pagados."
        )
    for entry in entries:
        c = contract_on(entry.date)
        if c is None:
            inp.warnings.append(f"Horas del {entry.date:%d/%m/%Y} fuera de contrato: no se pagan.")
            continue
        if c.pay_basis == EmploymentContract.PayBasis.MONTHLY:
            rate = inp.hourly_rate
        else:
            amount, source = books[c.pk].amount(entry.date)
            if amount is None:
                inp.warnings.append(f"Horas del {entry.date:%d/%m/%Y}: {source}.")
                continue
            rate = amount
            cba = books[c.pk].cba_rate(entry.date) if c.applies_cba else None
            if cba is not None and rate < cba:
                inp.warnings.append(
                    f"Tarifa {rate} inferior a la de la convención ({cba}) "
                    f"el {entry.date:%d/%m/%Y}."
                )
        inp.time_entry_ids.append(entry.pk)
        inp.entries.append(
            HoursEntry(
                date=entry.date,
                hour_type=entry.hour_type,
                day_kind=entry.day_kind,
                hours=entry.hours,
                rate=rate,
                cost_center_id=entry.cost_center_id,
            )
        )

    pending = WorkDay.objects.filter(employee=employee, date__gte=start, date__lte=end).exclude(
        status=WorkDay.Status.APPROVED
    )
    if pending.exists():
        inp.warnings.append(
            f"{pending.count()} jornada(s) del período sin aprobar: no se incluyen."
        )

    if contract.pay_basis == EmploymentContract.PayBasis.MONTHLY:
        unworked = WorkDay.objects.filter(
            employee=employee,
            date__gte=start,
            date__lte=end,
            status=WorkDay.Status.APPROVED,
            day_kind=WorkDay.DayKind.REGULAR,
        )
        inp.unworked_minutes = sum(w.missing_minutes for w in unworked)

    for d in RecurringDeduction.objects.filter(
        Q(end_date__isnull=True) | Q(end_date__gte=start),
        employee=employee,
        is_active=True,
        start_date__lte=end,
    ).select_related("concept"):
        if d.balance is not None and d.balance <= 0:
            continue
        inp.deductions.append(
            DeductionInput(
                id=d.pk,
                code=d.concept.code,
                name=d.concept.name,
                amount=d.amount_per_period,
                priority=d.concept.priority,
                legal_order=d.concept.is_legal_order,
                balance=d.balance,
            )
        )
    if params is not None:
        _add_vacations(inp, employee, contract, end, mode, params)
    return inp


def calculate(
    employee: Employee,
    start: date,
    end: date,
    pay_date: date | None = None,
    mode: str = "regular",
) -> PayResult:
    settings: PayrollSettings = settings_for_tenant()
    params = Parameters(settings.country, pay_date or end)
    inp = build_input(employee, start, end, mode, params)
    if not settings.deduct_unworked_time:
        inp.unworked_minutes = 0
    result = rules_for(settings.country).calculate(inp, params, settings)
    result.contract_id, result.pay_basis = inp.contract_id, inp.pay_basis
    result.time_entry_ids = list(inp.time_entry_ids)
    result.vacation_payments = {str(v.request_id): str(v.amount) for v in inp.vacations}
    return result


def decimo_earnings(employee: Employee, start: date, end: date) -> dict[Any, Decimal]:
    """Devengado por centro de costo en el cuatrimestre (planillas regulares y de vacaciones
    aprobadas cuyo período termina dentro del cuatrimestre)."""
    from django.db.models import Sum

    from .models import PayrollLineItem, PayrollRun

    rows = (
        PayrollLineItem.objects.filter(
            line__employee=employee,
            line__run__status__in=[PayrollRun.Status.APPROVED, PayrollRun.Status.PAID],
            line__run__run_type__in=[PayrollRun.RunType.REGULAR, PayrollRun.RunType.VACATION],
            line__run__period_end__gte=start,
            line__run__period_end__lte=end,
            kind="earning",
            concept__taxable_css=True,
        )
        .values("cost_center_id")
        .annotate(total=Sum("amount"))
    )
    return {r["cost_center_id"]: r["total"] for r in rows if r["total"]}


def calculate_decimo(employee: Employee, start: date, end: date, pay_date: date) -> PayResult:
    settings: PayrollSettings = settings_for_tenant()
    params = Parameters(settings.country, pay_date)
    contract = employee.contract_on(end) or employee.contracts.order_by("-start_date").first()
    if contract is None:
        raise PayrollInputError(f"{employee.full_name} no tiene contrato.")
    earnings = decimo_earnings(employee, start, end)
    rules = rules_for(settings.country)
    result = rules.calculate_decimo(earnings, contract.cost_center_id, params)
    result.contract_id, result.pay_basis = contract.pk, contract.pay_basis
    return result
