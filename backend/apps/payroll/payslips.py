"""Comprobantes de pago: generación, acumulados del año, ZIP y envío por correo."""

import io
import zipfile
from collections import defaultdict
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from apps.core.tenancy import require_current_tenant

from .models import PayrollLine, PayrollLineItem, PayrollRun, Payslip
from .payslip_pdf import PayslipData, PayslipRow, render
from .services import settings_for_tenant

PAID = (PayrollRun.Status.APPROVED, PayrollRun.Status.PAID)
YTD_CODES = (
    ("Devengado", None),
    ("Seguro Social", "CSS"),
    ("Seguro Educativo", "SE"),
    ("ISR retenido", "ISR"),
)


def _rows(items: list[PayrollLineItem], kind: str, merge: bool = True) -> list[PayslipRow]:
    if not merge:
        return [PayslipRow(i.name, i.amount, i.quantity, i.rate) for i in items if i.kind == kind]
    grouped: dict[tuple, PayslipRow] = {}
    for i in items:
        if i.kind != kind:
            continue
        key = (i.code, i.rate)
        if key in grouped:
            row = grouped[key]
            row.amount += i.amount
            if i.quantity is not None:
                row.quantity = (row.quantity or Decimal("0")) + i.quantity
        else:
            grouped[key] = PayslipRow(
                i.name, i.amount, i.quantity, i.rate if kind == "earning" else None
            )
    return list(grouped.values())


def year_to_date(line: PayrollLine) -> list[tuple[str, Decimal]]:
    run = line.run
    items = PayrollLineItem.objects.filter(
        line__employee_id=line.employee_id,
        line__run__status__in=[*PAID],
        line__run__pay_date__year=run.pay_date.year,
        line__run__pay_date__lte=run.pay_date,
    )
    if run.status not in PAID:  # vista previa antes de aprobar
        items = items | PayrollLineItem.objects.filter(line=line)
    totals: dict[str | None, Decimal] = defaultdict(lambda: Decimal("0"))
    for code, kind, total in items.values_list("code", "kind").annotate(total=Sum("amount")):
        if kind == "earning":
            totals[None] += total
        totals[code] += total
    return [(label, totals[code]) for label, code in YTD_CODES]


def build_data(line: PayrollLine, number: int, replaces: int | None = None) -> PayslipData:
    tenant = require_current_tenant()
    run, employee = line.run, line.employee
    items = list(
        line.items.select_related("cost_center", "concept").order_by("concept__priority", "code")
    )
    payroll_settings = settings_for_tenant()
    contract = line.contract
    if employee.payment_method == "ach" and employee.account_number:
        payment = f"ACH {employee.get_bank_display()} ****{employee.account_number[-4:]}"
    else:
        payment = employee.get_payment_method_display()
    centers = sorted({i.cost_center.code for i in items if i.cost_center and i.kind == "earning"})
    run_label = f"Planilla #{run.number} · {run.get_frequency_display()}"
    if run.project is not None:
        run_label += f" · {run.project.code}"
    return PayslipData(
        number=number,
        company_name=tenant.name,
        company_legal_name=tenant.legal_name or tenant.name,
        company_ruc=f"{tenant.ruc} DV {tenant.dv}".strip() if tenant.ruc else "",
        run_label=run_label,
        period_start=run.period_start,
        period_end=run.period_end,
        pay_date=run.pay_date,
        employee_name=employee.full_name,
        employee_code=employee.code,
        id_number=employee.id_number,
        css_number=employee.css_number,
        position=contract.position.name if contract else "",
        cost_centers=", ".join(centers),
        payment=payment,
        earnings=_rows(items, "earning"),
        deductions=_rows(items, "deduction"),
        gross=line.gross,
        total_deductions=line.deductions,
        net=line.net,
        employer=_rows(items, "employer") if payroll_settings.payslip_show_employer else [],
        year_to_date=year_to_date(line),
        replaces=replaces,
        generated_at=timezone.localtime(),
    )


def _next_number() -> int:
    return (Payslip.objects.aggregate(m=Max("number"))["m"] or 0) + 1


@transaction.atomic
def generate_for_run(run: PayrollRun) -> int:
    """Emite los comprobantes que falten (idempotente). Solo para planillas aprobadas."""
    if run.status not in PAID:
        raise ValueError("Los comprobantes se emiten al aprobar la planilla.")
    # Bloqueo para que dos procesos no repitan números.
    PayrollRun.objects.select_for_update().get(pk=run.pk)
    lines = (
        run.lines.filter(error="", payslip__isnull=True)
        .select_related("employee", "contract__position", "run__project")
        .order_by("employee__last_name", "employee__first_name")
    )
    number = _next_number()
    created = 0
    for line in lines:
        pdf = render(build_data(line, number))
        slip = Payslip(run=run, line=line, employee=line.employee, number=number, net=line.net)
        slip.pdf.save(f"{number:07d}.pdf", ContentFile(pdf), save=False)
        slip.save()
        number += 1
        created += 1
    return created


def zip_for_run(run: PayrollRun) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for slip in run.payslips.select_related("employee").order_by("number"):
            with slip.pdf.open("rb") as fh:
                name = f"{slip.number:07d}_{slip.employee.code}_{slip.employee.last_name}.pdf"
                archive.writestr(name, fh.read())
    return buffer.getvalue()


def email_payslips(slips: list[Payslip]) -> dict[str, Any]:
    """Envía cada comprobante al correo del empleado. Los que no tienen correo se reportan."""
    tenant = require_current_tenant()
    sent, missing = 0, []
    for slip in slips:
        employee = slip.employee
        if not employee.email:
            missing.append(employee.full_name)
            continue
        message = EmailMessage(
            subject=f"Comprobante de pago · {tenant.name} · {slip.run.pay_date:%d/%m/%Y}",
            body=(
                f"Hola {employee.first_name}:\n\n"
                f"Adjuntamos tu comprobante de pago No. {slip.number:07d} de la planilla del "
                f"{slip.run.period_start:%d/%m/%Y} al {slip.run.period_end:%d/%m/%Y}.\n\n"
                f"{tenant.name}"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[employee.email],
        )
        with slip.pdf.open("rb") as fh:
            message.attach(f"comprobante_{slip.number:07d}.pdf", fh.read(), "application/pdf")
        message.send()
        slip.emailed_at, slip.emailed_to = timezone.now(), employee.email
        slip.save(update_fields=["emailed_at", "emailed_to", "updated_at"])
        sent += 1
    return {"sent": sent, "missing_email": missing}
