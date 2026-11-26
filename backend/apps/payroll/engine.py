"""Tipos y utilidades del motor de planilla, independientes del país.

El cálculo de un empleado en un período recibe un `PayInput` ya preparado desde la base de
datos (contrato, salario y tarifas vigentes, horas aprobadas, descuentos) y devuelve un
`PayResult` con líneas explicadas. Las reglas de cada país (`apps.payroll_pa`) deciden qué
conceptos y tasas aplican; aquí están las piezas comunes: agrupar líneas, distribuir costos
por centro de costo y aplicar descuentos respetando la prioridad legal.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from apps.core.money import round_money

ZERO = Decimal("0")
PERIODS_PER_YEAR = {"weekly": 52, "biweekly": 24, "monthly": 12}


@dataclass
class HoursEntry:
    """Horas aprobadas de un día (attendance.TimeEntry) con la tarifa vigente ese día."""

    date: date
    hour_type: str  # ordinary | ot_day | ot_night | ot_mixed
    day_kind: str  # regular | rest | holiday
    hours: Decimal
    rate: Decimal
    cost_center_id: Any


@dataclass
class DeductionInput:
    id: Any
    code: str
    name: str
    amount: Decimal
    priority: int
    legal_order: bool
    balance: Decimal | None = None


@dataclass
class PayInput:
    employee_id: Any
    period_start: date
    period_end: date
    pay_basis: str  # monthly | hourly
    frequency: str  # weekly | biweekly | monthly
    default_cost_center_id: Any
    base_salary: Decimal = ZERO  # asalariados: salario del período ya prorrateado
    hourly_rate: Decimal = ZERO  # asalariados: valor hora para extras y descuentos
    entries: list[HoursEntry] = field(default_factory=list)
    unworked_minutes: int = 0
    union_member: bool = False
    deductions: list[DeductionInput] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    explanation: list[str] = field(default_factory=list)
    contract_id: Any = None
    time_entry_ids: list[Any] = field(default_factory=list)

    @property
    def periods_per_year(self) -> int:
        return PERIODS_PER_YEAR[self.frequency]


@dataclass
class Line:
    code: str
    name: str
    kind: str  # earning | deduction | employer | provision
    amount: Decimal
    quantity: Decimal | None = None
    rate: Decimal | None = None
    cost_center_id: Any = None
    taxable_css: bool = False
    taxable_se: bool = False
    taxable_isr: bool = False
    detail: str = ""
    source_id: Any = None  # p. ej. el descuento recurrente que originó la línea


@dataclass
class PayResult:
    lines: list[Line] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    explanation: list[str] = field(default_factory=list)
    parameters: dict[str, str] = field(default_factory=dict)
    contract_id: Any = None
    pay_basis: str = ""
    time_entry_ids: list[Any] = field(default_factory=list)

    def total(self, kind: str) -> Decimal:
        return sum((ln.amount for ln in self.lines if ln.kind == kind), ZERO)

    @property
    def gross(self) -> Decimal:
        return self.total("earning")

    @property
    def deductions(self) -> Decimal:
        return self.total("deduction")

    @property
    def net(self) -> Decimal:
        return self.gross - self.deductions

    @property
    def employer_cost(self) -> Decimal:
        return self.gross + self.total("employer") + self.total("provision")

    def base(self, flag: str) -> Decimal:
        return sum((ln.amount for ln in self.lines if getattr(ln, flag)), ZERO)


def merge_lines(lines: Iterable[Line]) -> list[Line]:
    """Agrupa líneas iguales (concepto, centro de costo y tarifa) sumando cantidad y monto."""
    grouped: dict[tuple, Line] = {}
    for ln in lines:
        key = (ln.code, ln.cost_center_id, ln.rate, ln.kind)
        if key in grouped:
            g = grouped[key]
            g.amount += ln.amount
            if ln.quantity is not None:
                g.quantity = (g.quantity or ZERO) + ln.quantity
        else:
            grouped[key] = Line(**{**ln.__dict__})
    result = list(grouped.values())
    for ln in result:
        ln.amount = round_money(ln.amount)
    return result


def cost_center_shares(earnings: Iterable[Line], fallback: Any) -> dict[Any, Decimal]:
    """Proporción del ingreso gravable por centro de costo (para distribuir aportes)."""
    totals: dict[Any, Decimal] = defaultdict(lambda: ZERO)
    for ln in earnings:
        if ln.kind == "earning" and ln.taxable_css:
            totals[ln.cost_center_id or fallback] += ln.amount
    total = sum(totals.values(), ZERO)
    if total <= 0:
        return {fallback: Decimal("1")}
    return {cc: amount / total for cc, amount in totals.items()}


def allocate(line: Line, shares: dict[Any, Decimal]) -> list[Line]:
    """Divide una línea entre centros de costo; el redondeo se ajusta en la última parte."""
    if len(shares) == 1:
        return [Line(**{**line.__dict__, "cost_center_id": next(iter(shares))})]
    parts, assigned = [], ZERO
    items = sorted(shares.items(), key=lambda kv: str(kv[0]))
    for i, (cc, share) in enumerate(items):
        amount = line.amount - assigned if i == len(items) - 1 else round_money(line.amount * share)
        assigned += amount
        parts.append(Line(**{**line.__dict__, "amount": amount, "cost_center_id": cc}))
    return parts


def apply_deductions(
    available: Decimal, deductions: Iterable[DeductionInput]
) -> tuple[list[Line], list[str]]:
    """Aplica los descuentos por prioridad sin dejar el neto en negativo. Las órdenes judiciales
    (pensión alimenticia, embargo) van primero dentro de su prioridad."""
    lines, warnings = [], []
    ordered = sorted(deductions, key=lambda d: (not d.legal_order, d.priority))
    for d in ordered:
        wanted = d.amount if d.balance is None else min(d.amount, d.balance)
        amount = round_money(min(wanted, max(available, ZERO)))
        if amount < wanted:
            warnings.append(
                f"{d.name}: se descontó {amount} de {round_money(wanted)} por salario insuficiente."
            )
        if amount <= 0:
            continue
        available -= amount
        lines.append(
            Line(code=d.code, name=d.name, kind="deduction", amount=amount, source_id=d.id)
        )
    return lines, warnings
