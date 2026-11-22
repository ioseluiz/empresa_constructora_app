from decimal import Decimal

import pytest

from apps.core.money import round_money


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("10.005", "10.01"),
        ("10.004", "10.00"),
        ("-2.345", "-2.35"),
        (Decimal("97.5") * Decimal("0.0975"), "9.51"),
    ],
)
def test_round_money(value: str | Decimal, expected: str) -> None:
    assert round_money(value) == Decimal(expected)


def test_float_rejected() -> None:
    with pytest.raises(TypeError):
        round_money(1.5)  # type: ignore[arg-type]
