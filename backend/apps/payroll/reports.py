"""Archivos de pago y reportes legales.

⚠️ Formatos:
- ACH: archivo genérico CSV con los datos que piden los bancos panameños. Cada banco (Banco
  General, Banistmo, BAC…) tiene su propio formato de carga: cuando el cliente entregue la
  especificación de su banco se agrega como un formato más en `ACH_FORMATS`.
- SIPE / Seguro Educativo: informe mensual en Excel con la base y las cuotas por empleado, para
  cargar o transcribir en el SIPE de la CSS. Validar el formato de carga vigente con la CSS.
"""

import csv
import io
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from apps.core.tenancy import require_current_tenant

from .models import PayrollLineItem, PayrollRun
from .services import settings_for_tenant

ACCOUNT_TYPE = {"savings": "Ahorros", "checking": "Corriente"}


@dataclass
class AchSummary:
    rows: list[dict[str, Any]] = field(default_factory=list)
    total: Decimal = Decimal("0")
    blocking: list[str] = field(default_factory=list)  # impiden generar el archivo
    warnings: list[str] = field(default_factory=list)
    non_ach: list[dict[str, Any]] = field(default_factory=list)  # cheque / efectivo


def ach_summary(run: PayrollRun) -> AchSummary:
    summary = AchSummary()
    settings = settings_for_tenant()
    routes: dict[str, str] = settings.ach_routes or {}
    if not settings.company_account_number:
        summary.warnings.append(
            "Falta la cuenta bancaria de la empresa (Planilla → Configuración)."
        )
    lines = (
        run.lines.filter(error="", net__gt=0)
        .select_related("employee")
        .order_by("employee__last_name", "employee__first_name")
    )
    for line in lines:
        e = line.employee
        if e.payment_method != "ach":
            summary.non_ach.append(
                {
                    "employee": e.full_name,
                    "method": e.get_payment_method_display(),
                    "amount": line.net,
                }
            )
            continue
        if not e.bank or not e.account_number:
            summary.blocking.append(f"{e.full_name}: faltan banco o número de cuenta.")
            continue
        route = routes.get(e.bank, "")
        if not route:
            summary.warnings.append(f"Sin código de ruta ACH para {e.get_bank_display()}.")
        summary.rows.append(
            {
                "name": e.full_name,
                "id_number": e.id_number,
                "bank": e.get_bank_display(),
                "route": route,
                "account_type": ACCOUNT_TYPE.get(e.account_type, ""),
                "account_number": e.account_number,
                "amount": line.net,
                "reference": f"PLANILLA {run.number} {run.pay_date:%d%m%Y}",
                "email": e.email,
            }
        )
        summary.total += line.net
    summary.warnings = sorted(set(summary.warnings))
    return summary


def _generic_csv(run: PayrollRun, summary: AchSummary) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "No.",
            "Beneficiario",
            "Cédula",
            "Banco",
            "Ruta",
            "Tipo de cuenta",
            "Cuenta",
            "Monto",
            "Referencia",
            "Correo",
        ]
    )
    for i, r in enumerate(summary.rows, start=1):
        writer.writerow(
            [
                i,
                r["name"],
                r["id_number"],
                r["bank"],
                r["route"],
                r["account_type"],
                r["account_number"],
                f"{r['amount']:.2f}",
                r["reference"],
                r["email"],
            ]
        )
    return out.getvalue().encode("utf-8-sig")


ACH_FORMATS: dict[str, tuple[str, Callable[[PayrollRun, AchSummary], bytes]]] = {
    "generic": ("CSV genérico", _generic_csv),
}


def ach_file(run: PayrollRun, fmt: str = "generic") -> tuple[str, bytes]:
    summary = ach_summary(run)
    if summary.blocking:
        raise ValueError("Corrige los datos bancarios: " + " ".join(summary.blocking))
    if not summary.rows:
        raise ValueError("Ningún empleado de la planilla cobra por ACH.")
    _, builder = ACH_FORMATS[fmt]
    return f"ach_planilla_{run.number}_{run.pay_date:%Y%m%d}.csv", builder(run, summary)


# --------------------------------------------------------------------------- SIPE / SE


def monthly_contributions(year: int, month: int) -> list[dict[str, Any]]:
    """Base y cuotas por empleado de las planillas aprobadas con fecha de pago en el mes."""
    items = PayrollLineItem.objects.filter(
        line__run__status__in=[PayrollRun.Status.APPROVED, PayrollRun.Status.PAID],
        line__run__pay_date__year=year,
        line__run__pay_date__month=month,
    ).select_related("concept", "line__employee")
    rows: dict[Any, dict[str, Any]] = {}
    for item in items:
        e = item.line.employee
        row = rows.setdefault(
            e.pk,
            {
                "employee": e,
                "css_base": Decimal("0"),
                "se_base": Decimal("0"),
                **{
                    k: Decimal("0")
                    for k in ("CSS", "CSS_PATRONAL", "SE", "SE_PATRONAL", "RIESGO_PROF", "ISR")
                },
            },
        )
        if item.kind == "earning":
            if item.concept is None or item.concept.taxable_css:
                row["css_base"] += item.amount
            if item.concept is None or item.concept.taxable_se:
                row["se_base"] += item.amount
        elif item.code in row:
            row[item.code] += item.amount
    return sorted(rows.values(), key=lambda r: (r["employee"].last_name, r["employee"].first_name))


def sipe_workbook(year: int, month: int) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    tenant = require_current_tenant()
    rows = monthly_contributions(year, month)
    wb = Workbook()
    bold = Font(bold=True)
    fill = PatternFill("solid", fgColor="E5E7EB")

    def header(ws: Any, title: str, columns: list[str]) -> None:
        ws.append([f"{tenant.legal_name or tenant.name} · RUC {tenant.ruc} DV {tenant.dv}"])
        ws.append([f"{title} · {month:02d}/{year}"])
        ws.append(["Informe base: validar con el formato de carga vigente del SIPE de la CSS."])
        ws.append([])
        ws.append(columns)
        for cell in ws[5]:
            cell.font, cell.fill = bold, fill
            cell.alignment = Alignment(horizontal="center", wrap_text=True)
        ws["A1"].font = Font(bold=True, size=12)

    ws = wb.active
    ws.title = "Seguro Social"
    cols = [
        "Cédula",
        "Nº seguro social",
        "Apellidos",
        "Nombres",
        "Salario (base CSS)",
        "Cuota empleado",
        "Cuota patronal",
        "Riesgos profesionales",
        "ISR retenido",
        "Total CSS",
    ]
    header(ws, "Planilla de cuotas de Seguro Social", cols)
    totals: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    for r in rows:
        e = r["employee"]
        values = [
            r["css_base"],
            r["CSS"],
            r["CSS_PATRONAL"],
            r["RIESGO_PROF"],
            r["ISR"],
            r["CSS"] + r["CSS_PATRONAL"] + r["RIESGO_PROF"],
        ]
        ws.append(
            [
                e.id_number,
                e.css_number,
                f"{e.last_name} {e.second_last_name}".strip(),
                f"{e.first_name} {e.middle_name}".strip(),
                *values,
            ]
        )
        for i, v in enumerate(values):
            totals[i] += v
    ws.append(["Totales", "", "", "", *[totals[i] for i in range(6)]])
    for cell in ws[ws.max_row]:
        cell.font = bold

    se = wb.create_sheet("Seguro Educativo")
    header(
        se,
        "Planilla de Seguro Educativo",
        ["Cédula", "Apellidos", "Nombres", "Salario", "Empleado", "Patronal", "Total"],
    )
    se_totals = [Decimal("0")] * 4
    for r in rows:
        e = r["employee"]
        values = [r["se_base"], r["SE"], r["SE_PATRONAL"], r["SE"] + r["SE_PATRONAL"]]
        se.append(
            [
                e.id_number,
                f"{e.last_name} {e.second_last_name}".strip(),
                f"{e.first_name} {e.middle_name}".strip(),
                *values,
            ]
        )
        se_totals = [a + b for a, b in zip(se_totals, values, strict=True)]
    se.append(["Totales", "", "", *se_totals])
    for cell in se[se.max_row]:
        cell.font = bold

    for sheet in (ws, se):
        for column in sheet.columns:
            letter = column[0].column_letter
            sheet.column_dimensions[letter].width = 16 if letter != "A" else 22
        for row in sheet.iter_rows(min_row=6):
            for cell in row:
                if isinstance(cell.value, Decimal):
                    cell.number_format = "#,##0.00"
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def month_bounds(value: str) -> tuple[int, int]:
    try:
        y, m = (int(x) for x in value.split("-"))
        date(y, m, 1)
    except (ValueError, TypeError) as exc:
        raise ValueError("Mes inválido: usa AAAA-MM.") from exc
    return y, m
