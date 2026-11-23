from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.core.tenancy import require_current_tenant
from apps.hr.models import Employee

from .importers import tabular, zkteco
from .importers.base import ImportFileError, ParsedRow
from .models import ClockCode, Device, ImportBatch, ImportRow, Punch


def normalize_code(code: str) -> str:
    """ "0012" y "12" son el mismo PIN en el reloj."""
    code = code.strip().upper()
    if code.isdigit():
        return code.lstrip("0") or "0"
    return code


class EmployeeResolver:
    """Resuelve el código del archivo al empleado, según la plantilla o los códigos de reloj."""

    def __init__(self, key: str) -> None:
        self.key = key
        self.global_codes: dict[str, int] = {}
        self.device_codes: dict[tuple[Any, str], Any] = {}
        self.employees: dict[Any, Employee] = {}
        if key == "clock_code":
            for c in ClockCode.objects.all():
                if c.device_id:
                    self.device_codes[(c.device_id, normalize_code(c.code))] = c.employee_id
                else:
                    self.global_codes[normalize_code(c.code)] = c.employee_id
            ids = {*self.global_codes.values(), *self.device_codes.values()}
            self.employees = {e.pk: e for e in Employee.objects.filter(pk__in=ids)}
            self.by_field: dict[str, Employee] = {}
        else:
            field = "code" if key == "employee_code" else "id_number"
            self.by_field = {getattr(e, field).upper(): e for e in Employee.objects.all()}

    def resolve(self, code: str, device: Device | None) -> Employee | None:
        if self.key != "clock_code":
            return self.by_field.get(code.upper())
        norm = normalize_code(code)
        pk = self.device_codes.get((device.pk, norm)) if device else None
        pk = pk or self.global_codes.get(norm)
        return self.employees.get(pk) if pk else None


class DeviceResolver:
    def __init__(self) -> None:
        devices = list(Device.objects.all())
        self.by_ref = {d.serial_number.upper(): d for d in devices if d.serial_number}
        self.by_ref.update({d.name.upper(): d for d in devices})

    def resolve(self, ref: str) -> Device | None:
        return self.by_ref.get(ref.strip().upper()) if ref.strip() else None


def parse_file(batch: ImportBatch) -> list[ParsedRow]:
    batch.file.open("rb")
    try:
        data = batch.file.read()
    finally:
        batch.file.close()
    if batch.source == ImportBatch.Source.ZKTECO:
        return zkteco.parse(data)
    return tabular.parse(data, batch.original_name, batch.template)


def process_batch(batch: ImportBatch) -> ImportBatch:
    """Interpreta el archivo y genera la vista previa (filas válidas, con error, duplicadas)."""
    batch.status = ImportBatch.Status.PROCESSING
    batch.save(update_fields=["status", "updated_at"])
    try:
        parsed = parse_file(batch)
    except ImportFileError as exc:
        batch.status, batch.error = ImportBatch.Status.FAILED, str(exc)
        batch.save(update_fields=["status", "error", "updated_at"])
        return batch

    tenant = require_current_tenant()  # bulk_create no pasa por save(): se fija a mano
    tz = ZoneInfo(tenant.timezone)
    key = batch.template.employee_key if batch.template else "clock_code"
    employees, devices = EmployeeResolver(key), DeviceResolver()
    now = timezone.now()
    rows: list[ImportRow] = []
    seen: set[tuple[Any, datetime]] = set()
    for p in parsed:
        row = ImportRow(
            tenant=tenant,
            batch=batch,
            row_number=p.row_number,
            raw=p.raw,
            raw_code=p.code[:60],
            direction=p.direction,
            status=ImportRow.Status.VALID,
        )
        rows.append(row)
        if p.error:
            row.status, row.message = ImportRow.Status.ERROR, p.error
            continue
        device = devices.resolve(p.device_ref) if p.device_ref else batch.device
        if p.device_ref and device is None:
            row.status, row.message = (
                ImportRow.Status.ERROR,
                f'Reloj "{p.device_ref}" no registrado.',
            )
            continue
        row.device = device
        employee = employees.resolve(p.code, device)
        assert p.timestamp is not None  # noqa: S101 - sin error siempre hay fecha
        row.timestamp = p.timestamp.replace(tzinfo=tz)
        if employee is None:
            row.status, row.message = (
                ImportRow.Status.ERROR,
                f'Código "{p.code}" sin empleado asociado.',
            )
            continue
        row.employee = employee
        day = row.timestamp.date()
        if row.timestamp > now + timedelta(minutes=5):
            row.status, row.message = ImportRow.Status.ERROR, "Fecha futura."
        elif day < employee.hire_date:
            row.status, row.message = ImportRow.Status.ERROR, "Anterior a la fecha de ingreso."
        elif employee.termination_date and day > employee.termination_date:
            row.status, row.message = ImportRow.Status.ERROR, "Posterior a la salida del empleado."
        elif (employee.pk, row.timestamp) in seen:
            row.status, row.message = ImportRow.Status.DUPLICATE, "Repetida en el archivo."
        else:
            seen.add((employee.pk, row.timestamp))

    _mark_existing_duplicates([r for r in rows if r.status == ImportRow.Status.VALID])
    ImportRow.objects.bulk_create(rows, batch_size=2000)
    valid = [r for r in rows if r.status == ImportRow.Status.VALID]
    batch.total_rows = len(rows)
    batch.valid_rows = len(valid)
    batch.error_rows = sum(r.status == ImportRow.Status.ERROR for r in rows)
    batch.duplicate_rows = sum(r.status == ImportRow.Status.DUPLICATE for r in rows)
    stamps = [r.timestamp for r in valid if r.timestamp]
    batch.first_punch, batch.last_punch = (min(stamps), max(stamps)) if stamps else (None, None)
    batch.status = ImportBatch.Status.PREVIEW
    batch.save()
    return batch


def _mark_existing_duplicates(rows: list[ImportRow]) -> None:
    if not rows:
        return
    stamps = [r.timestamp for r in rows if r.timestamp]
    existing = set(
        Punch.objects.filter(
            is_void=False,
            employee_id__in={r.employee_id for r in rows},
            timestamp__gte=min(stamps),
            timestamp__lte=max(stamps),
        ).values_list("employee_id", "timestamp")
    )
    for r in rows:
        if (r.employee_id, r.timestamp) in existing:
            r.status, r.message = ImportRow.Status.DUPLICATE, "Ya estaba registrada."


def row_project(row: ImportRow, batch: ImportBatch) -> Any:
    return (row.device.project_id if row.device else None) or batch.project_id


@transaction.atomic
def confirm_batch(batch: ImportBatch, user: Any) -> int:
    """Crea las marcaciones de las filas válidas. Devuelve cuántas se crearon."""
    valid = list(batch.rows.filter(status=ImportRow.Status.VALID).select_related("device"))
    _mark_existing_duplicates(valid)  # por si se registraron otras desde la vista previa
    source = Punch.Source.DEVICE if batch.source == ImportBatch.Source.ZKTECO else Punch.Source.FILE
    punches = []
    for row in valid:
        if row.status != ImportRow.Status.VALID or not row.employee_id or not row.timestamp:
            row.save(update_fields=["status", "message"])
            continue
        punches.append(
            Punch(
                tenant=batch.tenant,
                employee_id=row.employee_id,
                timestamp=row.timestamp,
                direction=row.direction or Punch.Direction.UNKNOWN,
                source=source,
                device=row.device,
                project_id=row_project(row, batch),
                batch=batch,
                created_by=user,
            )
        )
    Punch.objects.bulk_create(punches, batch_size=2000, ignore_conflicts=True)
    batch.valid_rows = len(punches)
    batch.duplicate_rows = batch.rows.filter(status=ImportRow.Status.DUPLICATE).count()
    batch.status = ImportBatch.Status.CONFIRMED
    batch.confirmed_at, batch.confirmed_by = timezone.now(), user
    batch.save()
    _recalculate(batch.punches.filter(is_void=False))
    return batch.punches.count()


@transaction.atomic
def revert_batch(batch: ImportBatch, user: Any, reason: str) -> int:
    """Anula todas las marcaciones vigentes del lote (no se borran)."""
    affected = list(batch.punches.filter(is_void=False).values_list("employee_id", "timestamp"))
    count = void_punches(batch.punches.filter(is_void=False), user, f"Lote revertido: {reason}")
    _recalculate_pairs(affected)
    batch.status = ImportBatch.Status.REVERTED
    batch.reverted_at, batch.reverted_by, batch.revert_reason = timezone.now(), user, reason
    batch.save()
    return count


def _recalculate_pairs(pairs: list[tuple[Any, Any]]) -> None:
    from .workdays import recalculate_for

    if pairs:
        recalculate_for(pairs)


def _recalculate(qs: Any) -> None:
    _recalculate_pairs(list(qs.values_list("employee_id", "timestamp")))


def void_punches(qs: Any, user: Any, reason: str) -> int:
    return qs.update(is_void=True, voided_at=timezone.now(), voided_by=user, void_reason=reason)


@transaction.atomic
def create_manual_punches(
    *,
    employees: Iterable[Employee],
    timestamp: datetime,
    direction: str,
    project: Any,
    reason: str,
    user: Any,
) -> tuple[list[Punch], list[Employee]]:
    """Registro manual (también por cuadrilla: la misma hora a varios empleados).
    Devuelve (creadas, omitidas por ya tener una marcación vigente en ese segundo)."""
    employees = list(employees)
    taken = set(
        Punch.objects.filter(
            is_void=False, timestamp=timestamp, employee__in=employees
        ).values_list("employee_id", flat=True)
    )
    created = [
        Punch.objects.create(
            employee=e,
            timestamp=timestamp,
            direction=direction,
            source=Punch.Source.MANUAL,
            project=project,
            reason=reason,
            created_by=user,
        )
        for e in employees
        if e.pk not in taken
    ]
    _recalculate_pairs([(p.employee_id, p.timestamp) for p in created])
    return created, [e for e in employees if e.pk in taken]


@transaction.atomic
def correct_punch(
    punch: Punch, *, timestamp: datetime, direction: str, reason: str, user: Any
) -> Punch:
    """Anula la marcación y crea la corregida, enlazada a la original."""
    void_punches(Punch.objects.filter(pk=punch.pk), user, f"Corregida: {reason}")
    new = Punch.objects.create(
        employee=punch.employee,
        timestamp=timestamp,
        direction=direction,
        source=Punch.Source.MANUAL,
        device=punch.device,
        project=punch.project,
        corrects=punch,
        reason=reason,
        created_by=user,
    )
    _recalculate_pairs([(punch.employee_id, punch.timestamp), (new.employee_id, new.timestamp)])
    return new


@transaction.atomic
def void_punch(punch: Punch, user: Any, reason: str) -> None:
    void_punches(Punch.objects.filter(pk=punch.pk), user, reason)
    _recalculate_pairs([(punch.employee_id, punch.timestamp)])


DEFAULT_SHIFT = {
    "code": "DIU",
    "name": "Diurno 7:00 a 16:00",
    "start_time": "07:00",
    "end_time": "16:00",
    "break_minutes": 60,
}


def bootstrap_timeclock() -> None:
    """Horario por defecto de una empresa nueva (editable). Requiere tenant activo."""
    from .models import Shift

    if not Shift.objects.filter(is_default=True).exists():
        Shift.objects.get_or_create(
            code=DEFAULT_SHIFT["code"], defaults={**DEFAULT_SHIFT, "is_default": True}
        )
