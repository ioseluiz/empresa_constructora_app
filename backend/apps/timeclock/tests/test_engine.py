"""Casos del motor de jornada. ⚠️ Los resultados esperados siguen la interpretación documentada
en engine.py y deben validarse con asesoría laboral panameña."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from apps.timeclock import engine
from apps.timeclock.engine import PunchData, ShiftRule

PA = ZoneInfo("America/Panama")
MON = date(2026, 11, 16)  # lunes
DAY_SHIFT = ShiftRule(start_time=time(7), end_time=time(16))  # 8 h pagadas + 1 h almuerzo
NIGHT_SHIFT = ShiftRule(start_time=time(22), end_time=time(6), workdays=(0, 1, 2, 3, 4, 5, 6))


def at(day: date, hh: int, mm: int = 0, ss: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hh, mm, ss, tzinfo=PA)


def p(ts: datetime, direction: str = "unknown", project=None) -> PunchData:
    return PunchData(ts, direction, project)


def run(punches, rule=DAY_SHIFT, kind="regular", day=MON):
    return engine.evaluate(day, punches, rule, kind, PA)


def test_regular_day_with_unpunched_lunch():
    r = run([p(at(MON, 6, 52), "in"), p(at(MON, 16, 1), "out")])
    assert r.jornada == "day"
    assert (r.worked_minutes, r.break_minutes, r.ordinary_minutes) == (481, 60, 480)
    assert r.overtime_minutes == 0 and r.late_minutes == 0 and r.missing_minutes == 0
    assert r.issues == []


def test_overtime_into_the_night_is_mixed_prolongation():
    # 7:00-18:40 con almuerzo: 8 h ordinarias, 2 h extra diurnas (16-18) y 40 min nocturnas
    # de una jornada iniciada de día (+75 %), redondeado a bloques de 15 min.
    r = run([p(at(MON, 7), "in"), p(at(MON, 18, 40), "out")])
    assert r.jornada == "day"
    assert r.ordinary_minutes == 480
    assert (r.overtime_day_minutes, r.overtime_night_minutes, r.overtime_mixed_minutes) == (
        120,
        0,
        30,
    )


def test_night_shift_crossing_midnight():
    tue = date(2026, 11, 17)
    r = run([p(at(MON, 21, 58)), p(at(tue, 6, 3))], rule=NIGHT_SHIFT)
    assert r.jornada == "night"
    assert r.first_in == at(MON, 22)  # llegada anticipada no pagada
    assert r.ordinary_minutes == 420  # máximo legal nocturno: 7 h
    assert r.overtime_minutes == 0  # 5 min no completan un bloque de 15


def test_night_overtime_is_fifty_percent():
    tue = date(2026, 11, 17)
    r = run([p(at(MON, 22)), p(at(tue, 7, 30))], rule=NIGHT_SHIFT)
    # 9.5 h - 1 h de descanso = 510; 420 ordinarias; extra 6:00-7:30 es diurna, antes nocturna.
    assert r.ordinary_minutes == 420
    assert r.overtime_night_minutes + r.overtime_day_minutes == 90
    assert r.overtime_mixed_minutes == 0


def test_late_arrival_beyond_tolerance():
    r = run([p(at(MON, 7, 20), "in"), p(at(MON, 16), "out")])
    assert r.late_minutes == 20 and "late" in r.issues
    assert r.ordinary_minutes == 460 and r.missing_minutes == 20


def test_arrival_within_tolerance_counts_full():
    r = run([p(at(MON, 7, 4), "in"), p(at(MON, 16), "out")])
    assert r.late_minutes == 0 and r.ordinary_minutes == 480


def test_punched_lunch_is_not_deducted_twice():
    r = run([p(at(MON, 7)), p(at(MON, 12)), p(at(MON, 13)), p(at(MON, 16))])
    assert r.break_minutes == 0
    assert r.worked_minutes == 480 and r.ordinary_minutes == 480


def test_double_tap_is_ignored_and_types_are_inferred():
    r = run([p(at(MON, 7)), p(at(MON, 7, 0, 40)), p(at(MON, 16))])
    assert r.issues == [] and r.ordinary_minutes == 480


@pytest.mark.parametrize(
    ("punches", "issue"),
    [
        ([p(at(MON, 7), "in")], "missing_out"),
        ([p(at(MON, 16), "out")], "missing_in"),
        ([p(at(MON, 7), "in"), p(at(MON, 9), "in"), p(at(MON, 16), "out")], "missing_out"),
    ],
)
def test_incomplete_punches_block_approval(punches, issue):
    r = run(punches)
    assert issue in r.issues
    assert engine.BLOCKING_ISSUES & set(r.issues)


def test_sunday_is_rest_day_without_lateness():
    sunday = date(2026, 11, 22)
    kind = engine.day_kind_for(sunday, DAY_SHIFT, holidays=[])
    r = run([p(at(sunday, 8)), p(at(sunday, 12))], kind=kind, day=sunday)
    assert kind == "rest"
    assert r.late_minutes == 0 and r.missing_minutes == 0 and r.ordinary_minutes == 240


def test_holiday_detection():
    assert engine.day_kind_for(date(2026, 11, 3), DAY_SHIFT, [date(2026, 11, 3)]) == "holiday"


def test_overtime_limit_and_excessive():
    r = run([p(at(MON, 7)), p(at(MON, 23, 30))])
    assert "overtime_limit" in r.issues
    tue = date(2026, 11, 17)
    r = run([p(at(MON, 7)), p(at(tue, 0, 30))])
    assert "excessive" in r.issues


def test_cluster_splits_days_and_keeps_night_shift_together():
    tue = date(2026, 11, 17)
    groups = engine.cluster(
        [p(at(MON, 7)), p(at(MON, 16)), p(at(MON, 22)), p(at(tue, 6)), p(at(tue, 14))]
    )
    assert [len(g) for g in groups] == [2, 2, 1]
    # Almuerzo marcado: sigue siendo una sola jornada.
    lunch = engine.cluster([p(at(MON, 7)), p(at(MON, 12)), p(at(MON, 13)), p(at(MON, 16))])
    assert len(lunch) == 1


def test_split_day_night():
    assert engine.split_day_night(at(MON, 17), at(MON, 19), PA) == (60, 60)
    tue = date(2026, 11, 17)
    assert engine.split_day_night(at(MON, 22), at(tue, 7), PA) == (60, 480)


def test_without_shift_uses_legal_maximum():
    r = run([p(at(MON, 7)), p(at(MON, 17))], rule=None)
    assert "no_shift" in r.issues
    assert r.ordinary_minutes == 480 and r.overtime_day_minutes == 120
