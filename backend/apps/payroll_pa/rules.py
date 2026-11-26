"""Reglas de planilla de Panamá (planilla regular).

⚠️ Interpretaciones a validar con contador / abogado laboral panameño (ver docs/PLAN.md §4.4):

1. Recargos: las horas se pagan tarifa × (1 + recargo del día) × (1 + recargo de extra).
   Día de descanso trabajado +50 %; feriado trabajado +150 %; extra diurna +25 %, nocturna
   +50 %, prolongación nocturna de jornada diurna +75 %. Los porcentajes son parámetros legales.
2. Asalariados: el salario del período cubre las horas ordinarias de días laborables. Las horas
   en días de descanso o feriado se pagan completas con su recargo, y las extras con el suyo.
   El tiempo no laborado de jornadas aprobadas (ausencias, tardanzas) se descuenta al valor hora
   si la empresa lo configura.
3. Por hora: cada hora aprobada se paga a la tarifa vigente ese día (fija o de la convención).
   No se paga aquí el feriado no trabajado ni el día de descanso (pendiente de definir).
4. ISR: se proyecta el ingreso del período a un año de 13 meses (incluye décimo), se aplica la
   tabla anual y se retiene la parte proporcional del período.
5. Valor hora de asalariados = salario mensual × 12 / (52 × horas semanales del contrato).
"""

from collections import defaultdict
from decimal import Decimal
from typing import Any

from apps.core.money import round_money
from apps.payroll.engine import (
    ZERO,
    Line,
    PayInput,
    PayResult,
    allocate,
    apply_deductions,
    cost_center_shares,
    merge_lines,
)
from apps.payroll.params import Parameters

# (código, nombre, tipo, CSS, SE, ISR, prioridad, orden judicial)
CONCEPTS: list[tuple[str, str, str, bool, bool, bool, int, bool]] = [
    ("SALARIO", "Salario", "earning", True, True, True, 10, False),
    ("HORAS_ORD", "Horas ordinarias", "earning", True, True, True, 11, False),
    ("DESCANSO_TRAB", "Horas en día de descanso (+50 %)", "earning", True, True, True, 12, False),
    ("FERIADO_TRAB", "Horas en feriado (+150 %)", "earning", True, True, True, 13, False),
    ("HE_DIURNA", "Horas extra diurnas (+25 %)", "earning", True, True, True, 20, False),
    ("HE_NOCTURNA", "Horas extra nocturnas (+50 %)", "earning", True, True, True, 21, False),
    (
        "HE_MIXTA",
        "Horas extra prolongación nocturna (+75 %)",
        "earning",
        True,
        True,
        True,
        22,
        False,
    ),
    ("TIEMPO_NO_LAB", "Tiempo no laborado", "earning", True, True, True, 30, False),
    ("VACACIONES", "Vacaciones", "earning", True, True, True, 40, False),
    ("DECIMO", "Décimo tercer mes", "earning", False, False, True, 50, False),
    ("CSS", "Seguro Social", "deduction", False, False, False, 10, False),
    ("SE", "Seguro Educativo", "deduction", False, False, False, 11, False),
    ("ISR", "Impuesto sobre la renta", "deduction", False, False, False, 12, False),
    ("CSS_DECIMO", "Seguro Social sobre décimo", "deduction", False, False, False, 13, False),
    ("PENSION_ALIM", "Pensión alimenticia", "deduction", False, False, False, 20, True),
    ("EMBARGO", "Embargo judicial", "deduction", False, False, False, 21, True),
    ("CUOTA_SINDICAL", "Cuota sindical", "deduction", False, False, False, 30, False),
    ("PRESTAMO", "Préstamo", "deduction", False, False, False, 40, False),
    ("DESC_AUTORIZADO", "Descuento autorizado", "deduction", False, False, False, 50, False),
    ("CSS_PATRONAL", "Seguro Social patronal", "employer", False, False, False, 10, False),
    ("SE_PATRONAL", "Seguro Educativo patronal", "employer", False, False, False, 11, False),
    ("RIESGO_PROF", "Riesgos profesionales", "employer", False, False, False, 12, False),
    (
        "CSS_DECIMO_PATRONAL",
        "Seguro Social patronal sobre décimo",
        "employer",
        False,
        False,
        False,
        13,
        False,
    ),
    ("PROV_DECIMO", "Provisión décimo tercer mes", "provision", False, False, False, 10, False),
    ("PROV_VACACIONES", "Provisión de vacaciones", "provision", False, False, False, 11, False),
    ("PROV_PRIMA", "Provisión prima de antigüedad", "provision", False, False, False, 12, False),
]
NAMES = {c[0]: c[1] for c in CONCEPTS}

OT_CONCEPT = {"ot_day": "HE_DIURNA", "ot_night": "HE_NOCTURNA", "ot_mixed": "HE_MIXTA"}
OT_PARAM = {
    "ot_day": "surcharge_overtime_day",
    "ot_night": "surcharge_overtime_night",
    "ot_mixed": "surcharge_overtime_mixed",
}
DAY_PARAM = {"rest": "surcharge_rest_day", "holiday": "surcharge_holiday"}
DAY_CONCEPT = {"regular": "HORAS_ORD", "rest": "DESCANSO_TRAB", "holiday": "FERIADO_TRAB"}


def earning(code: str, amount: Decimal, **kw: Any) -> Line:
    return Line(
        code=code,
        name=NAMES[code],
        kind="earning",
        amount=amount,
        taxable_css=True,
        taxable_se=True,
        taxable_isr=True,
        **kw,
    )


def isr_annual(income: Decimal, brackets: list[dict[str, Any]]) -> Decimal:
    """Impuesto anual según la tabla: [{"from", "to"|None, "rate", "fixed"}]."""
    for b in sorted(brackets, key=lambda b: Decimal(str(b["from"])), reverse=True):
        start = Decimal(str(b["from"]))
        if income > start:
            return Decimal(str(b.get("fixed", 0))) + (income - start) * Decimal(str(b["rate"]))
    return ZERO


class PanamaRules:
    country = "PA"

    def concepts(self) -> list[dict[str, Any]]:
        return [
            {
                "code": code,
                "name": name,
                "kind": kind,
                "taxable_css": css,
                "taxable_se": se,
                "taxable_isr": isr,
                "priority": priority,
                "is_legal_order": legal,
            }
            for code, name, kind, css, se, isr, priority, legal in CONCEPTS
        ]

    # ------------------------------------------------------------------ ingresos
    def earnings(self, inp: PayInput, p: Parameters) -> list[Line]:
        lines: list[Line] = []
        monthly = inp.pay_basis == "monthly"
        if monthly and inp.base_salary > 0:
            ordinary: dict[Any, Decimal] = defaultdict(lambda: ZERO)
            for e in inp.entries:
                if e.hour_type == "ordinary" and e.day_kind == "regular":
                    ordinary[e.cost_center_id] += e.hours
            shares = (
                {cc: h / sum(ordinary.values()) for cc, h in ordinary.items()}
                if ordinary
                else {inp.default_cost_center_id: Decimal("1")}
            )
            salary = earning("SALARIO", round_money(inp.base_salary), detail="Salario del período")
            lines.extend(allocate(salary, shares))

        for e in inp.entries:
            if monthly and e.hour_type == "ordinary" and e.day_kind == "regular":
                continue  # cubiertas por el salario
            day_factor = Decimal("1") + (
                p.rate(DAY_PARAM[e.day_kind]) if e.day_kind in DAY_PARAM else ZERO
            )
            if e.hour_type == "ordinary":
                code, factor = DAY_CONCEPT[e.day_kind], day_factor
            else:
                code = OT_CONCEPT[e.hour_type]
                factor = day_factor * (Decimal("1") + p.rate(OT_PARAM[e.hour_type]))
            rate = e.rate * factor
            lines.append(
                earning(
                    code,
                    e.hours * rate,
                    quantity=e.hours,
                    rate=rate.quantize(Decimal("0.0001")),
                    cost_center_id=e.cost_center_id,
                    detail=f"tarifa {e.rate} × {factor.normalize()}",
                )
            )

        for v in inp.vacations:
            lines.append(
                earning(
                    "VACACIONES",
                    v.amount,
                    quantity=Decimal(v.days),
                    rate=v.daily_rate,
                    cost_center_id=inp.default_cost_center_id,
                    detail=v.detail,
                )
            )

        if monthly and inp.unworked_minutes > 0:
            hours = (Decimal(inp.unworked_minutes) / 60).quantize(Decimal("0.01"))
            lines.append(
                earning(
                    "TIEMPO_NO_LAB",
                    -(hours * inp.hourly_rate),
                    quantity=hours,
                    rate=inp.hourly_rate,
                    cost_center_id=inp.default_cost_center_id,
                    detail="Ausencias, tardanzas o salidas anticipadas de jornadas aprobadas",
                )
            )
        return merge_lines(lines)

    # ------------------------------------------------------------------ cálculo completo
    def calculate(self, inp: PayInput, p: Parameters, settings: Any) -> PayResult:
        result = PayResult(warnings=list(inp.warnings), explanation=list(inp.explanation))
        result.lines = self.earnings(inp, p)
        css_base = max(result.base("taxable_css"), ZERO)
        se_base = max(result.base("taxable_se"), ZERO)
        isr_base = max(result.base("taxable_isr"), ZERO)

        statutory = [
            Line(
                "CSS",
                NAMES["CSS"],
                "deduction",
                round_money(css_base * p.rate("css_employee_rate")),
                rate=p.rate("css_employee_rate"),
                detail=f"base {round_money(css_base)}",
            ),
            Line(
                "SE",
                NAMES["SE"],
                "deduction",
                round_money(se_base * p.rate("se_employee_rate")),
                rate=p.rate("se_employee_rate"),
                detail=f"base {round_money(se_base)}",
            ),
        ]
        periods = Decimal(inp.periods_per_year)
        months = p.rate("isr_projection_months")
        annual = isr_base * periods * months / 12
        tax_annual = isr_annual(annual, p.table("isr_brackets"))
        isr = round_money(tax_annual * 12 / months / periods)
        statutory.append(
            Line(
                "ISR",
                NAMES["ISR"],
                "deduction",
                isr,
                detail=(
                    f"proyección anual {round_money(annual)} → "
                    f"impuesto anual {round_money(tax_annual)}"
                ),
            )
        )
        result.lines.extend(ln for ln in statutory if ln.amount > 0)

        available = result.gross - result.deductions
        others = list(inp.deductions)
        if inp.union_member and settings.union_dues_rate > 0:
            from apps.payroll.engine import DeductionInput

            others.append(
                DeductionInput(
                    id=None,
                    code="CUOTA_SINDICAL",
                    name=NAMES["CUOTA_SINDICAL"],
                    amount=round_money(result.gross * settings.union_dues_rate),
                    priority=30,
                    legal_order=False,
                )
            )
        deduction_lines, warnings = apply_deductions(available, others)
        result.lines.extend(deduction_lines)
        result.warnings.extend(warnings)

        shares = cost_center_shares(result.lines, inp.default_cost_center_id)
        employer = [
            ("CSS_PATRONAL", css_base, p.rate("css_employer_rate")),
            ("SE_PATRONAL", se_base, p.rate("se_employer_rate")),
            ("RIESGO_PROF", css_base, settings.occupational_risk_rate),
            ("PROV_DECIMO", css_base, p.rate("provision_decimo_rate")),
            ("PROV_VACACIONES", css_base, p.rate("provision_vacation_rate")),
            ("PROV_PRIMA", css_base, p.rate("provision_seniority_rate")),
        ]
        for code, base, rate in employer:
            amount = round_money(base * rate)
            if amount <= 0:
                continue
            kind = "provision" if code.startswith("PROV_") else "employer"
            line = Line(
                code, NAMES[code], kind, amount, rate=rate, detail=f"base {round_money(base)}"
            )
            result.lines.extend(allocate(line, shares))
        if settings.occupational_risk_rate <= 0:
            result.warnings.append(
                "La empresa no tiene configurada la tasa de riesgos profesionales."
            )
        result.parameters = p.used()
        return result

    # ------------------------------------------------------------------ décimo tercer mes
    def calculate_decimo(
        self, earnings_by_cost_center: dict[Any, Decimal], default_cost_center: Any, p: Parameters
    ) -> PayResult:
        """Partida del décimo: 1/12 de lo devengado en el cuatrimestre. CSS especial (empleado y
        patrono), sin Seguro Educativo. ISR: la partida equivale a 1/3 del décimo anual (≈ un
        salario mensual): se retiene impuesto(partida × 3 × 13) / 13 / 3. ⚠️ Validar."""
        result = PayResult()
        base = sum(earnings_by_cost_center.values(), ZERO)
        if base <= 0:
            result.warnings.append("Sin salario devengado en el cuatrimestre.")
            result.parameters = p.used()
            return result
        divisor = p.rate("decimo_divisor")
        decimo = round_money(base / divisor)
        shares = {
            cc or default_cost_center: amount / base
            for cc, amount in earnings_by_cost_center.items()
        }
        line = Line(
            "DECIMO",
            NAMES["DECIMO"],
            "earning",
            decimo,
            taxable_isr=True,
            detail=f"devengado {round_money(base)} / {divisor.normalize()}",
        )
        result.lines.extend(allocate(line, shares))
        css_rate = p.rate("css_decimo_employee_rate")
        result.lines.append(
            Line(
                "CSS_DECIMO",
                NAMES["CSS_DECIMO"],
                "deduction",
                round_money(decimo * css_rate),
                rate=css_rate,
                detail=f"base {decimo}",
            )
        )
        months = p.rate("isr_projection_months")
        tax = isr_annual(decimo * 3 * months, p.table("isr_brackets"))
        isr = round_money(tax / months / 3)
        if isr > 0:
            result.lines.append(
                Line(
                    "ISR",
                    NAMES["ISR"],
                    "deduction",
                    isr,
                    detail=f"proyección anual {round_money(decimo * 3 * months)}",
                )
            )
        employer_rate = p.rate("css_decimo_employer_rate")
        employer = Line(
            "CSS_DECIMO_PATRONAL",
            NAMES["CSS_DECIMO_PATRONAL"],
            "employer",
            round_money(decimo * employer_rate),
            rate=employer_rate,
            detail=f"base {decimo}",
        )
        result.lines.extend(allocate(employer, shares))
        result.explanation.append(
            f"Devengado del cuatrimestre {round_money(base)}: "
            f"décimo = {round_money(base)} / {divisor.normalize()}."
        )
        result.parameters = p.used()
        return result
