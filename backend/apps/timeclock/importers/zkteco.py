"""Archivo de marcaciones exportado por relojes ZKTeco (attlog.dat / *_attlog.dat / .txt).

Formato habitual, una marcación por línea separada por tabuladores:

    PIN  AAAA-MM-DD HH:MM:SS  verificación  estado  modo  código-de-trabajo

El estado (4.ª columna) suele ser 0 = entrada, 1 = salida, 4 = entrada de extra,
5 = salida de extra; 2 y 3 (salida/regreso de descanso) y otros valores se dejan "sin tipo"
para que el motor de jornada los infiera por secuencia. El significado exacto depende del
firmware y de cómo se configuró el equipo: validar con un archivo real del cliente.
"""

import re
from datetime import datetime

from .base import MAX_ROWS, ImportFileError, ParsedRow, decode_text

LINE = re.compile(
    r"^\s*(?P<pin>[^\s,;]+)[\s,;]+(?P<dt>\d{4}-\d{2}-\d{2}[ T]\d{1,2}:\d{2}(?::\d{2})?)"
    r"(?P<rest>.*)$"
)
STATE_TO_DIRECTION = {"0": "in", "4": "in", "1": "out", "5": "out"}


def parse(data: bytes) -> list[ParsedRow]:
    rows: list[ParsedRow] = []
    for number, line in enumerate(decode_text(data).splitlines(), start=1):
        if not line.strip():
            continue
        if len(rows) >= MAX_ROWS:
            raise ImportFileError(f"El archivo supera el máximo de {MAX_ROWS:,} marcaciones.")
        raw = line.strip()[:500]
        match = LINE.match(line)
        if not match:
            rows.append(ParsedRow(number, raw, error="Línea con formato no reconocido."))
            continue
        text = match["dt"].replace("T", " ")
        fmt = "%Y-%m-%d %H:%M:%S" if text.count(":") == 2 else "%Y-%m-%d %H:%M"
        try:
            timestamp = datetime.strptime(text, fmt)
        except ValueError:
            rows.append(ParsedRow(number, raw, code=match["pin"], error="Fecha u hora inválida."))
            continue
        fields = re.split(r"[\s,;]+", match["rest"].strip()) if match["rest"].strip() else []
        state = fields[1] if len(fields) >= 2 else ""
        rows.append(
            ParsedRow(
                number,
                raw,
                code=match["pin"],
                timestamp=timestamp,
                direction=STATE_TO_DIRECTION.get(state, "unknown"),
            )
        )
    if not rows:
        raise ImportFileError("El archivo no contiene marcaciones.")
    if all(r.error for r in rows):
        raise ImportFileError(
            "Ninguna línea tiene el formato de ZKTeco (código, fecha y hora). "
            "¿Es un Excel/CSV? Usa una plantilla de importación."
        )
    return rows
