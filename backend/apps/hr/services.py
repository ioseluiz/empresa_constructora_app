from datetime import date
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import IntegerField, Max, Q
from django.db.models.functions import Cast, Substr

from apps.organization.models import CostCenter
from apps.organization.services import HEAD_OFFICE_CODE

from .models import Employee, EmploymentContract, ProjectAssignment, SalaryRecord

CODE_PREFIX = "E-"


def next_employee_code() -> str:
    """Siguiente número correlativo E-0001, E-0002… (ignora códigos con otro formato)."""
    last = (
        Employee.objects.filter(code__regex=r"^E-\d+$")
        .annotate(n=Cast(Substr("code", len(CODE_PREFIX) + 1), IntegerField()))
        .aggregate(m=Max("n"))["m"]
    )
    return f"{CODE_PREFIX}{(last or 0) + 1:04d}"


def create_employee(**data: Any) -> Employee:
    if not data.get("code"):
        data["code"] = next_employee_code()
    return Employee.objects.create(**data)


def default_cost_center(project: Any) -> CostCenter:
    if project is not None:
        return project.cost_center
    return CostCenter.objects.get(code=HEAD_OFFICE_CODE)


def overlapping(qs: Any, start: date, end: date | None) -> Any:
    """Registros cuyo período [start_date, end_date] (NULL = abierto) se cruza con [start, end]."""
    qs = qs.filter(Q(end_date__isnull=True) | Q(end_date__gte=start))
    if end is not None:
        qs = qs.filter(start_date__lte=end)
    return qs


@transaction.atomic
def create_contract(
    *, initial_amount: Decimal | None, uses_cba_rate: bool, **data: Any
) -> EmploymentContract:
    if not data.get("cost_center"):
        data["cost_center"] = default_cost_center(data.get("project"))
    contract = EmploymentContract.objects.create(**data)
    SalaryRecord.objects.create(
        contract=contract,
        valid_from=contract.start_date,
        amount=None if uses_cba_rate else initial_amount,
        uses_cba_rate=uses_cba_rate,
        reason="Salario inicial",
        created_by=data.get("created_by"),
    )
    employee = contract.employee
    if contract.project_id:
        has_assignment = overlapping(
            employee.assignments.filter(project_id=contract.project_id),
            contract.start_date,
            contract.end_date,
        ).exists()
        if not has_assignment:
            ProjectAssignment.objects.create(
                employee=employee,
                project_id=contract.project_id,
                position=contract.position,
                start_date=contract.start_date,
                end_date=contract.end_date,
                created_by=data.get("created_by"),
            )
    if employee.status != Employee.Status.ACTIVE:
        employee.status = Employee.Status.ACTIVE
        employee.termination_date = None
        employee.save(update_fields=["status", "termination_date", "updated_at"])
    return contract


@transaction.atomic
def end_contract(
    contract: EmploymentContract, *, end_date: date, reason: str, user: Any = None
) -> EmploymentContract:
    """Termina el contrato. Si el empleado no tiene otro contrato vigente queda retirado y se
    cierran sus asignaciones abiertas. (El cálculo de la liquidación llega en el Sprint 12.)"""
    contract.end_date = end_date
    contract.end_reason = reason
    contract.status = EmploymentContract.Status.ENDED
    contract.updated_by = user
    contract.save()
    employee = contract.employee
    others = employee.contracts.filter(status=EmploymentContract.Status.ACTIVE).exclude(
        pk=contract.pk
    )
    if not others.filter(Q(end_date__isnull=True) | Q(end_date__gt=end_date)).exists():
        employee.assignments.filter(
            Q(end_date__isnull=True) | Q(end_date__gt=end_date), start_date__lte=end_date
        ).update(end_date=end_date)
        employee.status = Employee.Status.TERMINATED
        employee.termination_date = end_date
        employee.updated_by = user
        employee.save(update_fields=["status", "termination_date", "updated_by", "updated_at"])
    return contract
