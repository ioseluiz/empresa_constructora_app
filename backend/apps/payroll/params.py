"""Lectura de parámetros legales vigentes en una fecha."""

from datetime import date
from decimal import Decimal
from typing import Any

from .models import LegalParameter


class MissingParameter(LookupError):
    def __init__(self, country: str, key: str, on: date) -> None:
        super().__init__(f"Falta el parámetro legal {country}.{key} vigente al {on:%d/%m/%Y}.")


class Parameters:
    """Instantánea de los parámetros de un país vigentes en una fecha."""

    def __init__(self, country: str, on: date) -> None:
        self.country, self.on = country, on
        self._values: dict[str, LegalParameter] = {}
        for p in LegalParameter.objects.filter(country=country, valid_from__lte=on).order_by(
            "key", "-valid_from"
        ):
            self._values.setdefault(p.key, p)

    def _get(self, key: str) -> LegalParameter:
        try:
            return self._values[key]
        except KeyError:
            raise MissingParameter(self.country, key, self.on) from None

    def rate(self, key: str) -> Decimal:
        value = self._get(key).value
        if value is None:
            raise MissingParameter(self.country, key, self.on)
        return value

    def table(self, key: str) -> Any:
        value = self._get(key).table
        if value is None:
            raise MissingParameter(self.country, key, self.on)
        return value

    def used(self) -> dict[str, str]:
        """Parámetros y vigencias usados (se guardan con el cálculo para auditarlo)."""
        return {
            k: f"{p.value if p.value is not None else 'tabla'} desde {p.valid_from}"
            for k, p in self._values.items()
        }
