"""Utilidades de base de datos (PostgreSQL)."""

from django.contrib.postgres.fields import DateRangeField, RangeBoundary
from django.db.models import Func


class DateRange(Func):
    """`DATERANGE(inicio, fin, '[]')`: rango de fechas inclusivo; fin NULL = sin límite.
    Se usa en restricciones de exclusión para impedir períodos solapados."""

    function = "DATERANGE"
    output_field = DateRangeField()

    def __init__(self, start: str, end: str) -> None:
        super().__init__(start, end, RangeBoundary(inclusive_lower=True, inclusive_upper=True))
