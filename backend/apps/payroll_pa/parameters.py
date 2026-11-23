"""Valores de referencia iniciales de Panamá (docs/PLAN.md §4.4).

⚠️ Deben validarse con un contador panameño antes de producción. La Ley 462 de 2025 (reforma
de la CSS) aumenta la cuota patronal de forma escalonada: cargar cada tramo como una vigencia
nueva de `css_employer_rate` (no se precargan para no suponer fechas ni porcentajes).
"""

FROM = "2020-01-01"
VALIDATE = "Valor de referencia: validar con contador antes de usar en producción."

PARAMETERS: list[dict] = [
    {"key": "css_employee_rate", "name": "Seguro Social: cuota del empleado", "value": "0.0975"},
    {
        "key": "css_employer_rate",
        "name": "Seguro Social: cuota patronal",
        "value": "0.1225",
        "notes": (
            "La Ley 462 de 2025 la incrementa de forma escalonada: cargar cada nueva vigencia."
        ),
    },
    {"key": "se_employee_rate", "name": "Seguro Educativo: empleado", "value": "0.0125"},
    {"key": "se_employer_rate", "name": "Seguro Educativo: patronal", "value": "0.0150"},
    {"key": "css_decimo_employee_rate", "name": "CSS sobre décimo: empleado", "value": "0.0725"},
    {"key": "css_decimo_employer_rate", "name": "CSS sobre décimo: patronal", "value": "0.1075"},
    {
        "key": "isr_brackets",
        "name": "ISR: tabla anual de personas naturales",
        "table": [
            {"from": 0, "to": 11000, "rate": "0", "fixed": "0"},
            {"from": 11000, "to": 50000, "rate": "0.15", "fixed": "0"},
            {"from": 50000, "to": None, "rate": "0.25", "fixed": "5850"},
        ],
        "legal_basis": "Código Fiscal, art. 700",
    },
    {"key": "isr_projection_months", "name": "ISR: meses de la proyección anual", "value": "13"},
    {
        "key": "surcharge_overtime_day",
        "name": "Recargo hora extra diurna",
        "value": "0.25",
        "legal_basis": "Código de Trabajo, art. 33",
    },
    {"key": "surcharge_overtime_night", "name": "Recargo hora extra nocturna", "value": "0.50"},
    {
        "key": "surcharge_overtime_mixed",
        "name": "Recargo prolongación nocturna de jornada diurna",
        "value": "0.75",
    },
    {"key": "surcharge_rest_day", "name": "Recargo día de descanso trabajado", "value": "0.50"},
    {"key": "surcharge_holiday", "name": "Recargo feriado trabajado", "value": "1.50"},
    {
        "key": "provision_decimo_rate",
        "name": "Provisión décimo tercer mes (1/12)",
        "value": "0.083333",
    },
    {"key": "provision_vacation_rate", "name": "Provisión vacaciones (1/11)", "value": "0.090909"},
    {
        "key": "provision_seniority_rate",
        "name": "Provisión prima de antigüedad (1 semana por año)",
        "value": "0.019231",
    },
]
