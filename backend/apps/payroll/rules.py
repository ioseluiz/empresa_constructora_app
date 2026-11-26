"""Registro de paquetes de reglas por país (p. ej. `apps.payroll_pa`)."""

from typing import Any, Protocol


class CountryRules(Protocol):
    country: str

    def concepts(self) -> list[dict[str, Any]]: ...

    def calculate(self, inp: Any, params: Any, settings: Any) -> Any: ...


_registry: dict[str, CountryRules] = {}


def register(country: str, rules: CountryRules) -> None:
    _registry[country] = rules


def rules_for(country: str) -> CountryRules:
    try:
        return _registry[country]
    except KeyError:
        raise LookupError(f"No hay reglas de planilla para el país {country}.") from None
