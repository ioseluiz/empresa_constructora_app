"""Motor de jornada: de marcaciones crudas a una jornada clasificada según la ley panameña.

Funciones puras (sin base de datos) para poder probarlas exhaustivamente.

Reglas (Código de Trabajo de Panamá, arts. 30-36; validar con asesoría laboral):
- Período diurno 6:00-18:00; nocturno 18:00-6:00.
- Jornada diurna (todo en período diurno): máximo 8 h; nocturna: 7 h; mixta (abarca ambos
  períodos con 3 h nocturnas o menos): 7.5 h. Una mixta con más de 3 h nocturnas es nocturna.
- Lo trabajado por encima del máximo (o del horario, si es menor) es hora extra:
  diurna (+25 %), nocturna (+50 %) o prolongación en la noche de una jornada iniciada de día
  (+75 %, aquí "mixta"). Los recargos se aplican en la planilla, no aquí.
- Más de 3 h extra en un día se marca para revisión (límite legal).
- Domingo/día de descanso y feriado se identifican para que la planilla aplique su recargo.
"""

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

CLOSED_GAP = timedelta(hours=5)  # jornada cerrada + más de 5 h sin marcar = otra jornada
OPEN_MAX = timedelta(hours=16)  # máximo esperando la salida de una entrada abierta
DOUBLE_TAP = timedelta(minutes=2)  # marcaciones repetidas por error
DAY_START, NIGHT_START = time(6), time(18)
LEGAL_MAX = {"day": 8 * 60, "night": 7 * 60, "mixed": 7 * 60 + 30}
MIXED_MAX_NIGHT = 3 * 60
OVERTIME_DAILY_LIMIT = 3 * 60
EXCESSIVE_MINUTES = 16 * 60

# Inconsistencias que impiden aprobar (faltan datos para saber cuánto se trabajó).
BLOCKING_ISSUES = frozenset({"missing_in", "missing_out", "excessive"})
ISSUE_LABELS = {
    "missing_in": "Falta la entrada",
    "missing_out": "Falta la salida",
    "excessive": "Jornada excesiva (más de 16 h)",
    "late": "Llegada tardía",
    "absent": "Ausencia",
    "overtime_limit": "Más de 3 h extra en el día",
    "no_shift": "Sin horario asignado",
    "unassigned_project": "Marcó en un proyecto no asignado",
}


@dataclass(frozen=True)
class PunchData:
    timestamp: datetime  # con zona horaria
    direction: str  # in | out | unknown
    project_id: Any = None


@dataclass(frozen=True)
class ShiftRule:
    start_time: time
    end_time: time
    break_minutes: int = 60
    break_after_minutes: int = 360
    workdays: tuple[int, ...] = (0, 1, 2, 3, 4)
    late_tolerance_minutes: int = 5
    overtime_rounding_minutes: int = 15
    count_early_arrival: bool = False

    @property
    def span_minutes(self) -> int:
        start = self.start_time.hour * 60 + self.start_time.minute
        end = self.end_time.hour * 60 + self.end_time.minute
        return (end - start) % (24 * 60) or 24 * 60

    @property
    def paid_minutes(self) -> int:
        deduct = self.break_minutes if self.span_minutes > self.break_after_minutes else 0
        return self.span_minutes - deduct


@dataclass
class DayResult:
    date: date
    day_kind: str
    segments: list[tuple[datetime, datetime]] = field(default_factory=list)
    jornada: str = ""
    worked_minutes: int = 0
    break_minutes: int = 0
    ordinary_minutes: int = 0
    overtime_day_minutes: int = 0
    overtime_night_minutes: int = 0
    overtime_mixed_minutes: int = 0
    late_minutes: int = 0
    missing_minutes: int = 0
    issues: list[str] = field(default_factory=list)
    project_id: Any = None

    @property
    def first_in(self) -> datetime | None:
        return self.segments[0][0] if self.segments else None

    @property
    def last_out(self) -> datetime | None:
        return self.segments[-1][1] if self.segments else None

    @property
    def overtime_minutes(self) -> int:
        return self.overtime_day_minutes + self.overtime_night_minutes + self.overtime_mixed_minutes


def minutes(delta: timedelta) -> int:
    return int(delta.total_seconds() // 60)


def cluster(punches: Sequence[PunchData]) -> list[list[PunchData]]:
    """Agrupa marcaciones ordenadas en jornadas.

    Con una entrada abierta se espera la salida hasta 16 h (una jornada de 7:00 a 16:00 sin
    marcar almuerzo, o una nocturna de 22:00 a 06:00, quedan en un solo grupo). Con la jornada
    cerrada, un hueco de más de 5 h inicia otra jornada.
    """
    groups: list[list[PunchData]] = []
    is_open = False
    for punch in sorted(punches, key=lambda p: p.timestamp):
        if groups:
            gap = punch.timestamp - groups[-1][-1].timestamp
            if gap < DOUBLE_TAP:
                groups[-1].append(punch)
                continue
            limit = OPEN_MAX if is_open else CLOSED_GAP
            if gap <= limit:
                groups[-1].append(punch)
                is_open = _next_state(is_open, punch.direction)
                continue
        groups.append([punch])
        is_open = _next_state(False, punch.direction)
    return groups


def _next_state(is_open: bool, direction: str) -> bool:
    if direction == "unknown":
        return not is_open
    return direction == "in"


def pair(punches: Sequence[PunchData]) -> tuple[list[tuple[datetime, datetime]], set[str]]:
    """Empareja entradas y salidas. Las marcaciones sin tipo se infieren por secuencia y las
    repetidas en menos de 2 minutos se ignoran."""
    issues: set[str] = set()
    segments: list[tuple[datetime, datetime]] = []
    kept: list[PunchData] = []
    for p in punches:
        if kept and p.timestamp - kept[-1].timestamp < DOUBLE_TAP:
            continue
        kept.append(p)
    open_at: datetime | None = None
    for p in kept:
        direction = p.direction
        if direction == "unknown":
            direction = "in" if open_at is None else "out"
        if direction == "in":
            if open_at is not None:
                issues.add("missing_out")
            open_at = p.timestamp
        elif open_at is None:
            issues.add("missing_in")
        else:
            segments.append((open_at, p.timestamp))
            open_at = None
    if open_at is not None:
        issues.add("missing_out")
    return segments, issues


def split_day_night(start: datetime, end: datetime, tz: ZoneInfo) -> tuple[int, int]:
    """Minutos (diurnos, nocturnos) del intervalo, según la hora local."""
    day = night = 0
    cursor = start.astimezone(tz)
    end = end.astimezone(tz)
    while cursor < end:
        local = cursor.timetz().replace(tzinfo=None)
        is_day = DAY_START <= local < NIGHT_START
        boundary_time = NIGHT_START if is_day else DAY_START
        boundary = datetime.combine(cursor.date(), boundary_time, tz)
        if boundary <= cursor:
            boundary += timedelta(days=1)
        chunk_end = min(boundary, end)
        chunk = minutes(chunk_end - cursor)
        if is_day:
            day += chunk
        else:
            night += chunk
        cursor = chunk_end
    return day, night


def _apply_schedule(
    segments: list[tuple[datetime, datetime]], scheduled_start: datetime, rule: ShiftRule
) -> tuple[list[tuple[datetime, datetime]], int]:
    """Llegada anticipada no pagada y tolerancia de llegada. Devuelve tramos y tardanza."""
    start, end = segments[0]
    late = 0
    if start < scheduled_start and not rule.count_early_arrival and end > scheduled_start:
        start = scheduled_start
    elif start > scheduled_start:
        delay = minutes(start - scheduled_start)
        if delay <= rule.late_tolerance_minutes:
            start = scheduled_start
        else:
            late = delay
    return [(start, end), *segments[1:]], late


def _deduct_break(
    segments: list[tuple[datetime, datetime]], rule: ShiftRule | None
) -> tuple[list[tuple[datetime, datetime]], int]:
    """Si no marcó salida y regreso del almuerzo, se descuenta el descanso del horario
    (se ubica a mitad de la jornada pagada, p. ej. 11:00-12:00 en un horario de 7:00)."""
    if rule is None or len(segments) != 1 or not rule.break_minutes:
        return segments, 0
    start, end = segments[0]
    if minutes(end - start) <= rule.break_after_minutes:
        return segments, 0
    cut = start + timedelta(minutes=rule.paid_minutes // 2)
    resume = cut + timedelta(minutes=rule.break_minutes)
    if resume >= end:
        return segments, 0
    return [(start, cut), (resume, end)], rule.break_minutes


def _round_overtime(result: DayResult, block: int) -> None:
    if block <= 1:
        return
    excess = result.overtime_minutes % block
    for attr in ("overtime_mixed_minutes", "overtime_night_minutes", "overtime_day_minutes"):
        take = min(excess, getattr(result, attr))
        setattr(result, attr, getattr(result, attr) - take)
        excess -= take


def _classification_window(
    day: date,
    segments: list[tuple[datetime, datetime]],
    rule: ShiftRule | None,
    tz: ZoneInfo,
) -> list[tuple[datetime, datetime]]:
    if rule is not None:
        start = datetime.combine(day, rule.start_time, tz)
        return [(start, start + timedelta(minutes=rule.span_minutes))]
    window, remaining = [], LEGAL_MAX["day"]
    for s, e in segments:
        take = min(remaining, minutes(e - s))
        if take <= 0:
            break
        window.append((s, s + timedelta(minutes=take)))
        remaining -= take
    return window


def evaluate(
    day: date,
    punches: Sequence[PunchData],
    rule: ShiftRule | None,
    day_kind: str,
    tz: ZoneInfo,
) -> DayResult:
    """Calcula una jornada a partir de sus marcaciones (un grupo de `cluster`)."""
    result = DayResult(date=day, day_kind=day_kind)
    segments, issues = pair(punches)
    result.issues = sorted(issues)
    if rule is None:
        result.issues.append("no_shift")
    projects = Counter(p.project_id for p in punches if p.project_id)
    result.project_id = projects.most_common(1)[0][0] if projects else None
    if not segments:
        return result

    if rule is not None and day_kind == "regular":
        scheduled_start = datetime.combine(day, rule.start_time, tz)
        segments, result.late_minutes = _apply_schedule(segments, scheduled_start, rule)
        if result.late_minutes:
            result.issues.append("late")
    segments, result.break_minutes = _deduct_break(segments, rule)
    result.segments = segments
    result.worked_minutes = sum(minutes(e - s) for s, e in segments)

    # El tipo de jornada lo define el horario programado (las extras no lo cambian); sin
    # horario, las primeras 8 h trabajadas.
    day_total = night_total = 0
    for s, e in _classification_window(day, segments, rule, tz):
        d, n = split_day_night(s, e, tz)
        day_total, night_total = day_total + d, night_total + n
    if night_total == 0:
        result.jornada = "day"
    elif day_total == 0 or night_total > MIXED_MAX_NIGHT:
        result.jornada = "night"
    else:
        result.jornada = "mixed"

    budget = LEGAL_MAX[result.jornada]
    if rule is not None:
        budget = min(budget, rule.paid_minutes)
    started_in_day = DAY_START <= segments[0][0].astimezone(tz).time() < NIGHT_START
    remaining = budget
    for s, e in segments:
        length = minutes(e - s)
        ordinary = min(remaining, length)
        result.ordinary_minutes += ordinary
        remaining -= ordinary
        if ordinary < length:
            ot_day, ot_night = split_day_night(s + timedelta(minutes=ordinary), e, tz)
            result.overtime_day_minutes += ot_day
            if started_in_day:
                result.overtime_mixed_minutes += ot_night
            else:
                result.overtime_night_minutes += ot_night
    if rule is not None:
        _round_overtime(result, rule.overtime_rounding_minutes)
        if day_kind == "regular":
            result.missing_minutes = max(0, rule.paid_minutes - result.ordinary_minutes)
    if result.overtime_minutes > OVERTIME_DAILY_LIMIT:
        result.issues.append("overtime_limit")
    if result.worked_minutes > EXCESSIVE_MINUTES:
        result.issues.append("excessive")
    return result


def absence(day: date, rule: ShiftRule) -> DayResult:
    return DayResult(
        date=day, day_kind="regular", missing_minutes=rule.paid_minutes, issues=["absent"]
    )


def day_kind_for(day: date, rule: ShiftRule | None, holidays: Iterable[date]) -> str:
    if day in set(holidays):
        return "holiday"
    workdays = rule.workdays if rule is not None else (0, 1, 2, 3, 4, 5)
    return "regular" if day.weekday() in workdays else "rest"
