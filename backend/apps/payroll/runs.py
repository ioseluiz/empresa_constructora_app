"""Corridas de planilla: selección de empleados, cálculo, aprobación, pago y consolidado."""

from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import F, Max, Q, QuerySet, Sum
from django.utils import timezone

from apps.attendance.models import TimeEntry
from apps.core.tenancy import require_current_tenant
from apps.hr.models import Employee, EmploymentContract
from apps.organization.models import CostCenter

from .calculator import PayrollInputError, calculate, calculate_decimo
from .engine import ZERO
from .models import PayrollConcept, PayrollLine, PayrollLineItem, PayrollRun, RecurringDeduction
from .params import MissingParameter

ACTIVE = (
    PayrollRun.Status.DRAFT,
    PayrollRun.Status.CALCULATED,
    PayrollRun.Status.APPROVED,
    PayrollRun.Status.PAID,
)


class RunError(Exception):
    pass


def decimo_periods(year: int) -> list[tuple[date, date, date]]:
    """(inicio, fin, fecha de pago) de las tres partidas del décimo del año."""
    return [
        (date(year - 1, 12, 16), date(year, 4, 15), date(year, 4, 15)),
        (date(year, 4, 16), date(year, 8, 15), date(year, 8, 15)),
        (date(year, 8, 16), date(year, 12, 15), date(year, 12, 15)),
    ]


def next_number() -> int:
    return (PayrollRun.objects.aggregate(m=Max("number"))["m"] or 0) + 1


@transaction.atomic
def create_run(**data: Any) -> PayrollRun:
    if data["scope"] != PayrollRun.Scope.PROJECT:
        data["project"] = None
    return PayrollRun.objects.create(number=next_number(), **data)


def contracts_in_scope(run: PayrollRun) -> QuerySet[EmploymentContract]:
    qs = (
        EmploymentContract.objects.exclude(status=EmploymentContract.Status.CANCELLED)
        .filter(start_date__lte=run.period_end)
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=run.period_start))
        .select_related("employee", "cost_center")
    )
    if run.run_type == PayrollRun.RunType.REGULAR:
        qs = qs.filter(pay_frequency=run.frequency)
    if run.scope == PayrollRun.Scope.PROJECT and run.project is not None:
        qs = qs.filter(Q(project=run.project) | Q(cost_center=run.project.cost_center))
    elif run.scope == PayrollRun.Scope.OFFICE:
        qs = qs.filter(project__isnull=True).exclude(cost_center__kind=CostCenter.Kind.PROJECT)
    return qs


def employees_for(run: PayrollRun) -> tuple[list[Employee], list[str]]:
    """Empleados del alcance. Se excluye a quien ya esté en otra corrida activa del mismo tipo
    que se cruce con el período (para no pagarle dos veces)."""
    employees: dict[Any, Employee] = {}
    for contract in contracts_in_scope(run).order_by("start_date"):
        employees[contract.employee_id] = contract.employee
    if run.run_type == PayrollRun.RunType.VACATION:
        from apps.leave.models import VacationRequest

        with_vacations = set(
            VacationRequest.objects.filter(
                status=VacationRequest.Status.APPROVED,
                payment_mode=VacationRequest.PaymentMode.SEPARATE,
                paid_line__isnull=True,
                start_date__lte=run.period_end,
            ).values_list("employee_id", flat=True)
        )
        employees = {k: v for k, v in employees.items() if k in with_vacations}
    taken = dict(
        PayrollLine.objects.filter(
            run__status__in=ACTIVE,
            run__run_type=run.run_type,
            run__period_start__lte=run.period_end,
            run__period_end__gte=run.period_start,
            employee_id__in=list(employees),
        )
        .exclude(run=run)
        .values_list("employee_id", "run__number")
    )
    skipped = [
        f"{employees[eid].full_name} ya está en la planilla #{number}."
        for eid, number in taken.items()
    ]
    chosen = [e for eid, e in employees.items() if eid not in taken]
    return sorted(chosen, key=lambda e: (e.last_name, e.first_name)), skipped


@transaction.atomic
def calculate_run(run: PayrollRun, user: Any) -> PayrollRun:
    if not run.is_editable:
        raise RunError("Solo se calculan planillas en borrador o calculadas.")
    tenant = require_current_tenant()
    run.lines.all().delete()
    concepts = {c.code: c for c in PayrollConcept.objects.all()}
    employees, skipped = employees_for(run)
    no_earnings: list[str] = []
    parameters: dict[str, str] = {}
    totals = dict.fromkeys(("gross", "deductions", "net", "employer", "provision"), ZERO)
    for employee in employees:
        line = PayrollLine(tenant=tenant, run=run, employee=employee)
        try:
            if run.run_type == PayrollRun.RunType.DECIMO:
                result = calculate_decimo(employee, run.period_start, run.period_end, run.pay_date)
                if result.gross <= 0:
                    no_earnings.append(employee.full_name)
                    continue
            else:
                mode = "vacation" if run.run_type == PayrollRun.RunType.VACATION else "regular"
                result = calculate(employee, run.period_start, run.period_end, run.pay_date, mode)
        except (PayrollInputError, MissingParameter, LookupError) as exc:
            line.error = str(exc)[:255]
            line.save()
            continue
        parameters = parameters or result.parameters
        line.contract_id, line.pay_basis = result.contract_id, result.pay_basis
        line.gross, line.deductions, line.net = result.gross, result.deductions, result.net
        line.employer_contributions = result.total("employer")
        line.provisions = result.total("provision")
        line.warnings, line.explanation = result.warnings, result.explanation
        line.time_entry_ids = result.time_entry_ids
        line.vacation_payments = result.vacation_payments
        line.save()
        PayrollLineItem.objects.bulk_create(
            [
                PayrollLineItem(
                    tenant=tenant,
                    line=line,
                    concept=concepts.get(ln.code),
                    code=ln.code,
                    name=ln.name,
                    kind=ln.kind,
                    quantity=ln.quantity,
                    rate=ln.rate,
                    amount=ln.amount,
                    cost_center_id=ln.cost_center_id,
                    detail=ln.detail[:255],
                    deduction_id=ln.source_id if ln.kind == "deduction" else None,
                )
                for ln in result.lines
            ]
        )
        totals["gross"] += result.gross
        totals["deductions"] += result.deductions
        totals["net"] += result.net
        totals["employer"] += result.total("employer")
        totals["provision"] += result.total("provision")

    if no_earnings:
        skipped.append(f"{len(no_earnings)} sin salario devengado en el período")
    run.employee_count = len(employees) - len(no_earnings)
    run.gross, run.deductions, run.net = totals["gross"], totals["deductions"], totals["net"]
    run.employer_contributions, run.provisions = totals["employer"], totals["provision"]
    run.parameters = parameters
    run.notes = ("; ".join(skipped))[:255]
    run.status = PayrollRun.Status.CALCULATED
    run.calculated_at, run.calculated_by = timezone.now(), user
    run.save()
    return run


@transaction.atomic
def approve_run(run: PayrollRun, user: Any) -> PayrollRun:
    run = PayrollRun.objects.select_for_update().get(pk=run.pk)
    if run.status != PayrollRun.Status.CALCULATED:
        raise RunError("Solo se aprueban planillas calculadas.")
    lines = list(run.lines.all())
    if not lines:
        raise RunError("La planilla no tiene empleados.")
    errors = [ln for ln in lines if ln.error]
    if errors:
        raise RunError(f"{len(errors)} empleado(s) con error: corrígelos y recalcula.")
    entry_ids = [eid for ln in lines for eid in ln.time_entry_ids]
    already = TimeEntry.objects.filter(pk__in=entry_ids, locked=True).count()
    if already:
        raise RunError(
            f"{already} registro(s) de horas ya se pagaron en otra planilla: "
            "recalcula esta planilla."
        )
    TimeEntry.objects.filter(pk__in=entry_ids).update(locked=True)
    # Vacaciones pagadas en esta planilla.
    from apps.leave.models import VacationRequest

    for line in lines:
        for request_id, amount in (line.vacation_payments or {}).items():
            updated = VacationRequest.objects.filter(pk=request_id, paid_line__isnull=True).update(
                paid_line=line, paid_amount=Decimal(amount)
            )
            if not updated:
                raise RunError(
                    "Unas vacaciones ya se pagaron en otra planilla: recalcula esta planilla."
                )
    # Abonos a préstamos y demás descuentos con saldo.
    for item in PayrollLineItem.objects.filter(line__run=run, deduction__isnull=False):
        RecurringDeduction.objects.filter(pk=item.deduction_id).update(
            paid_amount=F("paid_amount") + item.amount
        )
    RecurringDeduction.objects.filter(
        total_amount__isnull=False, paid_amount__gte=F("total_amount"), is_active=True
    ).update(is_active=False)
    run.status = PayrollRun.Status.APPROVED
    run.approved_at, run.approved_by = timezone.now(), user
    run.save(update_fields=["status", "approved_at", "approved_by", "updated_at"])
    return run


def mark_paid(run: PayrollRun, user: Any) -> PayrollRun:
    if run.status != PayrollRun.Status.APPROVED:
        raise RunError("Solo se marcan como pagadas las planillas aprobadas.")
    run.status = PayrollRun.Status.PAID
    run.paid_at, run.paid_by = timezone.now(), user
    run.save(update_fields=["status", "paid_at", "paid_by", "updated_at"])
    return run


def cancel_run(run: PayrollRun, user: Any) -> PayrollRun:
    if not run.is_editable:
        raise RunError(
            "Una planilla aprobada no se anula: corrige con ajustes en el siguiente período."
        )
    run.status = PayrollRun.Status.CANCELLED
    run.updated_by = user
    run.save(update_fields=["status", "updated_by", "updated_at"])
    return run


def consolidated(runs: Iterable[PayrollRun]) -> dict[str, Any]:
    """Planilla global: totales por centro de costo y por concepto de las corridas dadas."""
    run_ids = [r.pk for r in runs]
    items = PayrollLineItem.objects.filter(line__run_id__in=run_ids)
    by_cost_center: dict[Any, dict[str, Any]] = {}
    for row in items.values("cost_center__code", "cost_center__name", "kind").annotate(
        total=Sum("amount")
    ):
        key = row["cost_center__code"] or "—"
        entry = by_cost_center.setdefault(
            key,
            {
                "cost_center": row["cost_center__code"],
                "name": row["cost_center__name"] or "Sin centro de costo (deducciones)",
                "earning": Decimal("0"),
                "employer": Decimal("0"),
                "provision": Decimal("0"),
                "deduction": Decimal("0"),
            },
        )
        entry[row["kind"]] = row["total"]
    for entry in by_cost_center.values():
        entry["total_cost"] = entry["earning"] + entry["employer"] + entry["provision"]
    by_concept = list(
        items.values("code", "name", "kind").annotate(total=Sum("amount")).order_by("kind", "code")
    )
    totals = PayrollRun.objects.filter(pk__in=run_ids).aggregate(
        gross=Sum("gross"),
        deductions=Sum("deductions"),
        net=Sum("net"),
        employer_contributions=Sum("employer_contributions"),
        provisions=Sum("provisions"),
    )
    employees = PayrollLine.objects.filter(run_id__in=run_ids).values("employee").distinct().count()
    return {
        "runs": len(run_ids),
        "employees": employees,
        "totals": {k: v or Decimal("0") for k, v in totals.items()},
        "by_cost_center": sorted(
            (e for e in by_cost_center.values() if e["cost_center"]), key=lambda e: e["cost_center"]
        ),
        "by_concept": by_concept,
    }


def runs_paid_between(
    date_from: date, date_to: date, include_calculated: bool = False
) -> QuerySet[PayrollRun]:
    statuses = [PayrollRun.Status.APPROVED, PayrollRun.Status.PAID]
    if include_calculated:
        statuses.append(PayrollRun.Status.CALCULATED)
    return PayrollRun.objects.filter(
        status__in=statuses, pay_date__gte=date_from, pay_date__lte=date_to
    )
