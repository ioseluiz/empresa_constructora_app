"""Utilidades de redondeo monetario. Toda la aritmética de planilla usa Decimal."""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def to_decimal(value: Decimal | int | str) -> Decimal:
    if isinstance(value, float):
        raise TypeError("No se permiten floats en montos; use Decimal o str.")
    return value if isinstance(value, Decimal) else Decimal(value)


def round_money(value: Decimal | int | str) -> Decimal:
    """Redondea a centavos con la regla comercial (mitad hacia arriba)."""
    return to_decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)
