from dataclasses import dataclass
from datetime import datetime

MAX_ROWS = 100_000


class ImportFileError(Exception):
    """El archivo completo no se puede leer (formato equivocado, vacío, demasiado grande…)."""


@dataclass
class ParsedRow:
    row_number: int
    raw: str
    code: str = ""
    timestamp: datetime | None = None  # hora local sin zona (la del reloj)
    direction: str = "unknown"  # in | out | unknown
    device_ref: str = ""
    error: str = ""


def decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ImportFileError("No se pudo leer el archivo como texto.")
