"""PDF del comprobante de pago (ReportLab)."""

import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

INK = colors.HexColor("#111827")
MUTED = colors.HexColor("#6B7280")
LINE = colors.HexColor("#E5E7EB")
BRAND = colors.HexColor("#1D4ED8")
SOFT = colors.HexColor("#EFF6FF")


@dataclass
class PayslipRow:
    name: str
    amount: Decimal
    quantity: Decimal | None = None
    rate: Decimal | None = None


@dataclass
class PayslipData:
    number: int
    company_name: str
    company_legal_name: str
    company_ruc: str
    run_label: str
    period_start: date
    period_end: date
    pay_date: date
    employee_name: str
    employee_code: str
    id_number: str
    css_number: str
    position: str
    cost_centers: str
    payment: str
    earnings: list[PayslipRow]
    deductions: list[PayslipRow]
    gross: Decimal
    total_deductions: Decimal
    net: Decimal
    employer: list[PayslipRow] = field(default_factory=list)
    year_to_date: list[tuple[str, Decimal]] = field(default_factory=list)
    replaces: int | None = None
    generated_at: datetime | None = None


def money(value: Decimal | None) -> str:
    if value is None:
        return ""
    sign = "-" if value < 0 else ""
    return f"{sign}B/. {abs(value):,.2f}"


def fmt_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def number(value: Decimal | None, places: int = 2) -> str:
    return "" if value is None else f"{value:,.{places}f}"


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["Normal"]
    return {
        "body": ParagraphStyle(
            "body", parent=base, fontName="Helvetica", fontSize=8.5, leading=11, textColor=INK
        ),
        "muted": ParagraphStyle(
            "muted", parent=base, fontName="Helvetica", fontSize=7.5, leading=10, textColor=MUTED
        ),
        "title": ParagraphStyle(
            "title", parent=base, fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=INK
        ),
        "doc": ParagraphStyle(
            "doc",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=BRAND,
            alignment=TA_RIGHT,
        ),
        "right": ParagraphStyle(
            "right", parent=base, fontName="Helvetica", fontSize=8.5, leading=11, alignment=TA_RIGHT
        ),
        "section": ParagraphStyle(
            "section",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=INK,
            spaceBefore=4,
        ),
    }


def _table(
    rows: list[list[str]],
    widths: list[float],
    header: bool = True,
    right_from: int = 1,
    bold_last: bool = False,
) -> Table:
    t = Table(rows, colWidths=widths, hAlign="LEFT")
    style = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("ALIGN", (right_from, 0), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if bold_last:
        style += [
            ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 8.5),
            ("LINEABOVE", (0, -1), (-1, -1), 0.8, INK),
        ]
    if header:
        style += [
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.5),
            ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
        ]
    t.setStyle(TableStyle(style))
    return t


def render(data: PayslipData) -> bytes:
    s = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Comprobante de pago {data.number:07d}",
        author=data.company_name,
    )
    width = doc.width
    story: list = []

    header = Table(
        [
            [
                [
                    Paragraph(data.company_name, s["title"]),
                    Paragraph(data.company_legal_name, s["muted"]),
                    Paragraph(f"RUC {data.company_ruc}" if data.company_ruc else "", s["muted"]),
                ],
                [
                    Paragraph("COMPROBANTE DE PAGO", s["doc"]),
                    Paragraph(f"No. {data.number:07d}", s["right"]),
                    Paragraph(data.run_label, s["right"]),
                ],
            ]
        ],
        colWidths=[width * 0.6, width * 0.4],
    )
    header.setStyle(
        TableStyle(
            [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 1.2, BRAND)]
        )
    )
    story += [header, Spacer(1, 5 * mm)]

    info = [
        [
            "Empleado",
            data.employee_name,
            "Período",
            f"{fmt_date(data.period_start)} al {fmt_date(data.period_end)}",
        ],
        ["Nº de empleado", data.employee_code, "Fecha de pago", fmt_date(data.pay_date)],
        ["Cédula", data.id_number, "Seguro social", data.css_number or "—"],
        ["Puesto", data.position or "—", "Centro de costo", data.cost_centers or "—"],
        ["Forma de pago", data.payment, "", ""],
    ]
    info_table = Table(info, colWidths=[width * 0.16, width * 0.34, width * 0.16, width * 0.34])
    info_table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
                ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 7.5),
                ("FONT", (2, 0), (2, -1), "Helvetica-Bold", 7.5),
                ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
                ("TEXTCOLOR", (2, 0), (2, -1), MUTED),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F9FAFB")),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story += [info_table, Spacer(1, 5 * mm)]

    story.append(Paragraph("Ingresos", s["section"]))
    earnings = [["Concepto", "Cantidad", "Tarifa", "Monto"]] + [
        [r.name, number(r.quantity), number(r.rate, 4) if r.rate else "", money(r.amount)]
        for r in data.earnings
    ]
    earnings.append(["Total ingresos", "", "", money(data.gross)])
    t = _table(earnings, [width * 0.52, width * 0.14, width * 0.14, width * 0.2], bold_last=True)
    story += [t, Spacer(1, 3 * mm)]

    story.append(Paragraph("Deducciones", s["section"]))
    deductions = [["Concepto", "Monto"]] + [[r.name, money(r.amount)] for r in data.deductions]
    deductions.append(["Total deducciones", money(data.total_deductions)])
    t = _table(deductions, [width * 0.8, width * 0.2], bold_last=True)
    story += [t, Spacer(1, 4 * mm)]

    net = Table([["NETO A PAGAR", money(data.net)]], colWidths=[width * 0.7, width * 0.3])
    net.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica-Bold", 12),
                ("TEXTCOLOR", (0, 0), (-1, -1), BRAND),
                ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story += [net, Spacer(1, 5 * mm)]

    if data.employer:
        story.append(Paragraph("Aportes del empleador (informativo)", s["section"]))
        rows = [["Concepto", "Monto"]] + [[r.name, money(r.amount)] for r in data.employer]
        story += [_table(rows, [width * 0.8, width * 0.2]), Spacer(1, 4 * mm)]

    if data.year_to_date:
        story.append(Paragraph(f"Acumulado del año {data.pay_date.year}", s["section"]))
        rows = [[label for label, _ in data.year_to_date], [money(v) for _, v in data.year_to_date]]
        n = len(data.year_to_date)
        story += [_table(rows, [width / n] * n, right_from=0), Spacer(1, 8 * mm)]

    signature = Table(
        [["", "", ""], ["Recibí conforme", "", "Fecha"]],
        colWidths=[width * 0.5, width * 0.1, width * 0.25],
        hAlign="LEFT",
    )
    signature.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 1), (0, 1), 0.6, INK),
                ("LINEABOVE", (2, 1), (2, 1), 0.6, INK),
                ("FONT", (0, 1), (-1, 1), "Helvetica", 7.5),
                ("TEXTCOLOR", (0, 1), (-1, 1), MUTED),
                ("TOPPADDING", (0, 0), (-1, 0), 18),
            ]
        )
    )
    story.append(signature)
    note = (
        f"Comprobante emitido el {data.generated_at:%d/%m/%Y %H:%M}." if data.generated_at else ""
    )
    if data.replaces:
        note += f" Reemplaza al comprobante No. {data.replaces:07d}."
    story += [Spacer(1, 6 * mm), Paragraph(note, s["muted"])]
    doc.build(story)
    return buffer.getvalue()
