"""Excel (.xlsx) o CSV de otros sistemas, interpretado con una `ImportTemplate`."""

import csv
import io
from collections.abc import Iterable, Sequence
from datetime import date, datetime, time
from typing import Any

from .base import MAX_ROWS, ImportFileError, ParsedRow, decode_text


def read_table(data: bytes, filename: str, delimiter: str = "") -> list[list[Any]]:
    if filename.lower().endswith((".xlsx", ".xlsm")):
        return _read_xlsx(data)
    if filename.lower().endswith(".xls"):
        raise ImportFileError(
            "Formato .xls antiguo no soportado: guarda el archivo como .xlsx o CSV."
        )
    text = decode_text(data)
    if not delimiter:
        try:
            delimiter = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
    return list(csv.reader(io.StringIO(text), delimiter=delimiter))


def _read_xlsx(data: bytes) -> list[list[Any]]:
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # archivo dañado o que no es Excel
        raise ImportFileError("No se pudo abrir el archivo de Excel.") from exc
    sheet = workbook.worksheets[0]
    rows: list[list[Any]] = []
    for values in sheet.iter_rows(values_only=True):
        if len(rows) > MAX_ROWS + 1:
            break
        rows.append(list(values))
    workbook.close()
    return rows


def _is_blank(row: Sequence[Any]) -> bool:
    return all(v is None or str(v).strip() == "" for v in row)


class ColumnResolver:
    def __init__(self, header: Sequence[Any] | None) -> None:
        self.by_name = (
            {str(name).strip().lower(): i for i, name in enumerate(header) if name is not None}
            if header
            else {}
        )

    def index(self, ref: str, label: str) -> int | None:
        ref = (ref or "").strip()
        if not ref:
            return None
        if ref.isdigit():
            return int(ref) - 1
        if ref.lower() in self.by_name:
            return self.by_name[ref.lower()]
        raise ImportFileError(f'No se encontró la columna "{ref}" ({label}) en el encabezado.')


def _cell(row: Sequence[Any], index: int | None) -> Any:
    if index is None or index >= len(row):
        return None
    value = row[index]
    return value.strip() if isinstance(value, str) else value


def _parse_date(value: Any, fmt: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), fmt).date()


def _parse_time(value: Any, fmt: str) -> time:
    if isinstance(value, datetime):
        return value.time()
    if isinstance(value, time):
        return value
    text = str(value)
    for candidate in (fmt, f"{fmt}:%S", "%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M:%S %p"):
        try:
            return datetime.strptime(text.upper(), candidate).time()
        except ValueError:
            continue
    raise ValueError(text)


def _values(text: str) -> set[str]:
    return {v.strip().upper() for v in text.split(",") if v.strip()}


def parse(data: bytes, filename: str, template: Any) -> list[ParsedRow]:
    table = read_table(data, filename, template.delimiter)
    if not table:
        raise ImportFileError("El archivo está vacío.")
    header = table[0] if template.has_header else None
    body: Iterable[tuple[int, list[Any]]] = enumerate(
        table[1:] if template.has_header else table, start=2 if template.has_header else 1
    )
    cols = ColumnResolver(header)
    emp = cols.index(template.employee_column, "empleado")
    dt = cols.index(template.datetime_column, "fecha y hora")
    d = cols.index(template.date_column, "fecha")
    t = cols.index(template.time_column, "hora")
    direction_col = cols.index(template.direction_column, "tipo")
    device_col = cols.index(template.device_column, "reloj")
    if dt is None and (d is None or t is None):
        raise ImportFileError(
            "La plantilla debe indicar la columna de fecha y hora, o ambas por separado."
        )
    ins, outs = _values(template.in_values), _values(template.out_values)

    rows: list[ParsedRow] = []
    for number, row in body:
        if _is_blank(row):
            continue
        if len(rows) >= MAX_ROWS:
            raise ImportFileError(f"El archivo supera el máximo de {MAX_ROWS:,} marcaciones.")
        raw = " | ".join("" if v is None else str(v) for v in row)[:500]
        code = _cell(row, emp)
        parsed = ParsedRow(number, raw, code="" if code is None else _normalize_code(code))
        if not parsed.code:
            parsed.error = "Falta el empleado."
            rows.append(parsed)
            continue
        try:
            if dt is not None:
                value = _cell(row, dt)
                if isinstance(value, datetime):
                    parsed.timestamp = value
                else:
                    day_text, _, time_text = str(value).partition(" ")
                    parsed.timestamp = datetime.combine(
                        _parse_date(day_text, template.date_format),
                        _parse_time(time_text.strip(), template.time_format),
                    )
            else:
                parsed.timestamp = datetime.combine(
                    _parse_date(_cell(row, d), template.date_format),
                    _parse_time(_cell(row, t), template.time_format),
                )
            parsed.timestamp = parsed.timestamp.replace(microsecond=0, tzinfo=None)
        except (ValueError, TypeError):
            parsed.error = "Fecha u hora inválida (revisa el formato de la plantilla)."
        marker = str(_cell(row, direction_col) or "").strip().upper()
        parsed.direction = "in" if marker in ins else "out" if marker in outs else "unknown"
        parsed.device_ref = str(_cell(row, device_col) or "")
        rows.append(parsed)
    if not rows:
        raise ImportFileError("El archivo no contiene marcaciones.")
    return rows


def _normalize_code(value: Any) -> str:
    # Excel convierte "0012" en 12.0: se normalizan números enteros.
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip().upper()
