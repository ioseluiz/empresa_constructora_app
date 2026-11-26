"""Casos de referencia de la planilla regular de Panamá (calculados a mano).

⚠️ Siguen las interpretaciones documentadas en apps/payroll_pa/rules.py y los valores de
referencia de apps/payroll_pa/parameters.py: deben validarse con un contador panameño.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from apps.payroll.engine import DeductionInput, HoursEntry, PayInput
from apps.payroll.params import MissingParameter, Parameters
from apps.payroll_pa.rules import PanamaRules, isr_annual

pytestmark = pytest.mark.django_db
D = Decimal
RULES = PanamaRules()
DAY = date(2026, 11, 16)


@dataclass
class Settings:
    occupational_risk_rate: Decimal = Decimal("0.0567")
    union_dues_rate: Decimal = Decimal("0")


@pytest.fixture
def params():
    return Parameters("PA", date(2026, 11, 30))


def amounts(result):
    out: dict[str, Decimal] = {}
    for ln in result.lines:
        out[ln.code] = out.get(ln.code, D("0")) + ln.amount
    return out


def test_isr_brackets(params):
    table = params.table("isr_brackets")
    assert isr_annual(D("10000"), table) == 0
    assert isr_annual(D("20000"), table) == D("1350.00")
    assert isr_annual(D("60000"), table) == D("8350.00")


def test_monthly_salary(params):
    inp = PayInput(
        employee_id=1,
        period_start=date(2026, 11, 1),
        period_end=date(2026, 11, 30),
        pay_basis="monthly",
        frequency="monthly",
        default_cost_center_id="OC",
        base_salary=D("1500"),
        hourly_rate=D("7.2115"),
    )
    r = RULES.calculate(inp, params, Settings())
    a = amounts(r)
    assert a["SALARIO"] == D("1500.00")
    assert (a["CSS"], a["SE"]) == (D("146.25"), D("18.75"))
    # ISR: 1500 × 13 = 19,500 → (19,500 - 11,000) × 15 % = 1,275 anual → 1,275 / 13 = 98.08
    assert a["ISR"] == D("98.08")
    assert r.net == D("1236.92")
    assert (a["CSS_PATRONAL"], a["SE_PATRONAL"], a["RIESGO_PROF"]) == (
        D("183.75"),
        D("22.50"),
        D("85.05"),
    )
    assert (a["PROV_DECIMO"], a["PROV_VACACIONES"], a["PROV_PRIMA"]) == (
        D("125.00"),
        D("136.36"),
        D("28.85"),
    )
    assert all(ln.cost_center_id == "OC" for ln in r.lines if ln.kind in ("employer", "provision"))


def hours(hour_type, day_kind, qty, cc="P1", rate="4.55"):
    return HoursEntry(DAY, hour_type, day_kind, D(qty), D(rate), cc)


def test_hourly_week_with_surcharges(params):
    inp = PayInput(
        employee_id=1,
        period_start=date(2026, 11, 16),
        period_end=date(2026, 11, 22),
        pay_basis="hourly",
        frequency="weekly",
        default_cost_center_id="P1",
        entries=[
            hours("ordinary", "regular", "40"),
            hours("ot_day", "regular", "2"),
            hours("ot_mixed", "regular", "0.5"),
            hours("ordinary", "rest", "4"),
            hours("ordinary", "holiday", "8"),
        ],
    )
    r = RULES.calculate(inp, params, Settings())
    a = amounts(r)
    assert a["HORAS_ORD"] == D("182.00")  # 40 × 4.55
    assert a["HE_DIURNA"] == D("11.38")  # 2 × 4.55 × 1.25
    assert a["HE_MIXTA"] == D("3.98")  # 0.5 × 4.55 × 1.75
    assert a["DESCANSO_TRAB"] == D("27.30")  # 4 × 4.55 × 1.5
    assert a["FERIADO_TRAB"] == D("91.00")  # 8 × 4.55 × 2.5
    assert r.gross == D("315.66")
    assert (a["CSS"], a["SE"]) == (D("30.78"), D("3.95"))
    annual = D("315.66") * 52 * 13 / 12
    expected_isr = (isr_annual(annual, params.table("isr_brackets")) * 12 / 13 / 52).quantize(
        D("0.01")
    )
    assert a["ISR"] == expected_isr == D("18.06")


def test_overtime_on_rest_day_compounds(params):
    inp = PayInput(
        1, DAY, DAY, "hourly", "weekly", "P1", entries=[hours("ot_day", "rest", "1", rate="4")]
    )
    a = amounts(RULES.calculate(inp, params, Settings()))
    assert a["HE_DIURNA"] == D("7.50")  # 4 × 1.5 × 1.25


def test_monthly_employee_overtime_and_unworked_time(params):
    inp = PayInput(
        employee_id=1,
        period_start=date(2026, 11, 1),
        period_end=date(2026, 11, 15),
        pay_basis="monthly",
        frequency="biweekly",
        default_cost_center_id="OC",
        base_salary=D("600"),
        hourly_rate=D("5.7692"),
        unworked_minutes=90,
        entries=[
            hours("ordinary", "regular", "80", cc="OC"),
            hours("ot_night", "regular", "1", cc="OC", rate="5.7692"),
        ],
    )
    a = amounts(RULES.calculate(inp, params, Settings()))
    assert "HORAS_ORD" not in a  # cubiertas por el salario
    assert a["HE_NOCTURNA"] == D("8.65")  # 5.7692 × 1.5
    assert a["TIEMPO_NO_LAB"] == D("-8.65")  # 1.5 h × 5.7692


def test_cost_center_allocation_sums_exactly(params):
    inp = PayInput(
        1,
        DAY,
        DAY,
        "hourly",
        "weekly",
        "P1",
        entries=[
            hours("ordinary", "regular", "30", cc="P1"),
            hours("ordinary", "regular", "10.33", cc="P2"),
        ],
    )
    r = RULES.calculate(inp, params, Settings())
    css_lines = [ln for ln in r.lines if ln.code == "CSS_PATRONAL"]
    assert {ln.cost_center_id for ln in css_lines} == {"P1", "P2"}
    css_base = r.base("taxable_css")
    assert sum(ln.amount for ln in css_lines) == (css_base * D("0.1225")).quantize(D("0.01"))


def test_deductions_priority_legal_orders_first_and_never_negative(params):
    inp = PayInput(
        1,
        DAY,
        DAY,
        "hourly",
        "weekly",
        "P1",
        entries=[hours("ordinary", "regular", "20")],  # 91.00 bruto
        deductions=[
            DeductionInput(1, "PRESTAMO", "Préstamo", D("60"), 40, False, balance=D("500")),
            DeductionInput(2, "PENSION_ALIM", "Pensión alimenticia", D("50"), 20, True),
        ],
    )
    r = RULES.calculate(inp, params, Settings())
    a = amounts(r)
    assert a["PENSION_ALIM"] == D("50.00")
    available = D("91.00") - a["CSS"] - a["SE"]
    assert a["PRESTAMO"] == available - D("50.00")
    assert r.net == 0
    assert any("Préstamo" in w for w in r.warnings)


def test_loan_stops_at_balance(params):
    inp = PayInput(
        1,
        DAY,
        DAY,
        "hourly",
        "weekly",
        "P1",
        entries=[hours("ordinary", "regular", "40")],
        deductions=[DeductionInput(1, "PRESTAMO", "Préstamo", D("60"), 40, False, balance=D("25"))],
    )
    assert amounts(RULES.calculate(inp, params, Settings()))["PRESTAMO"] == D("25.00")


def test_union_dues_for_members(params):
    inp = PayInput(
        1,
        DAY,
        DAY,
        "hourly",
        "weekly",
        "P1",
        union_member=True,
        entries=[hours("ordinary", "regular", "40", rate="5")],
    )
    a = amounts(RULES.calculate(inp, params, Settings(union_dues_rate=D("0.02"))))
    assert a["CUOTA_SINDICAL"] == D("4.00")


def test_parameters_are_effective_dated():
    from apps.payroll.models import LegalParameter

    LegalParameter.objects.create(
        country="PA",
        key="css_employer_rate",
        name="CSS patronal",
        value=D("0.1325"),
        valid_from=date(2027, 1, 1),
    )
    assert Parameters("PA", date(2026, 12, 31)).rate("css_employer_rate") == D("0.1225")
    assert Parameters("PA", date(2027, 1, 15)).rate("css_employer_rate") == D("0.1325")
    with pytest.raises(MissingParameter):
        Parameters("PA", date(2019, 1, 1)).rate("css_employee_rate")
