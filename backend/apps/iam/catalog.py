"""Catálogo de permisos de la plataforma (definido en código, versionado con la app).

Cada módulo nuevo agrega aquí sus permisos. Los roles de cada empresa son combinaciones
de estos códigos. Convención: `<recurso>.<acción>`; `view` para leer y `manage` para
crear/editar/eliminar, más acciones específicas (approve, import…).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Perm:
    code: str
    label: str
    module: str


PERMISSIONS: tuple[Perm, ...] = (
    # Administración
    Perm("tenant.manage", "Editar datos y políticas de la empresa", "Administración"),
    Perm("users.view", "Ver usuarios", "Administración"),
    Perm("users.manage", "Invitar, editar y desactivar usuarios", "Administración"),
    Perm("roles.manage", "Crear y editar roles", "Administración"),
    Perm("audit.view", "Ver bitácora de auditoría", "Administración"),
    # Proyectos (Sprint 4)
    Perm("projects.view", "Ver proyectos y centros de costo", "Proyectos"),
    Perm("projects.manage", "Crear y editar proyectos", "Proyectos"),
    # Recursos humanos (Sprint 5)
    Perm("hr.employee.view", "Ver empleados", "Recursos humanos"),
    Perm("hr.employee.manage", "Crear y editar empleados y contratos", "Recursos humanos"),
    Perm("hr.salary.view", "Ver salarios y tarifas", "Recursos humanos"),
    # Marcaciones (Sprints 6-7)
    Perm("timeclock.view", "Ver marcaciones y jornadas", "Marcaciones"),
    Perm("timeclock.import", "Importar marcaciones", "Marcaciones"),
    Perm("timeclock.manual", "Registrar y corregir marcaciones manualmente", "Marcaciones"),
    Perm("timeclock.approve", "Aprobar jornadas", "Marcaciones"),
    # Planilla (Sprints 8-12)
    Perm("payroll.view", "Ver planillas", "Planilla"),
    Perm("payroll.calculate", "Calcular y preparar planillas", "Planilla"),
    Perm("payroll.approve", "Aprobar planillas", "Planilla"),
    Perm("payroll.config", "Configurar conceptos y parámetros legales", "Planilla"),
    Perm("payroll.reports", "Generar reportes legales y archivos de pago", "Planilla"),
    # Vacaciones (Sprint 11)
    Perm("leave.view", "Ver vacaciones y licencias", "Vacaciones"),
    Perm("leave.manage", "Registrar vacaciones y licencias", "Vacaciones"),
    Perm("leave.approve", "Aprobar vacaciones", "Vacaciones"),
)

PERMISSION_CODES: frozenset[str] = frozenset(p.code for p in PERMISSIONS)
ALL = sorted(PERMISSION_CODES)


def _all_view() -> list[str]:
    return sorted(c for c in PERMISSION_CODES if c.endswith(".view"))


# Plantillas que se crean en cada empresa nueva (docs/PLAN.md §3.2). Son editables.
DEFAULT_ROLES: dict[str, dict] = {
    "Administrador": {"description": "Acceso total a la empresa.", "permissions": ALL},
    "Gerente general": {
        "description": "Ve toda la información y aprueba planillas.",
        "permissions": sorted({*_all_view(), "hr.salary.view", "payroll.approve", "leave.approve"}),
    },
    "Recursos humanos": {
        "description": "Gestiona empleados, contratos y vacaciones.",
        "permissions": [
            "projects.view",
            "hr.employee.view",
            "hr.employee.manage",
            "hr.salary.view",
            "timeclock.view",
            "leave.view",
            "leave.manage",
            "leave.approve",
            "users.view",
        ],
    },
    "Planillero": {
        "description": "Importa marcaciones y calcula planillas.",
        "permissions": [
            "projects.view",
            "hr.employee.view",
            "hr.salary.view",
            "timeclock.view",
            "timeclock.import",
            "timeclock.manual",
            "payroll.view",
            "payroll.calculate",
            "payroll.reports",
            "leave.view",
        ],
    },
    "Contador": {
        "description": "Consulta planillas y genera reportes legales.",
        "permissions": [
            "projects.view",
            "hr.employee.view",
            "hr.salary.view",
            "payroll.view",
            "payroll.reports",
            "payroll.config",
            "leave.view",
        ],
    },
    "Jefe de proyecto": {
        "description": "Ve el personal de sus obras y aprueba jornadas y vacaciones.",
        "permissions": [
            "projects.view",
            "hr.employee.view",
            "timeclock.view",
            "timeclock.approve",
            "leave.view",
            "leave.approve",
        ],
    },
    "Supervisor de obra": {
        "description": "Registra y corrige marcaciones de su cuadrilla.",
        "permissions": ["projects.view", "hr.employee.view", "timeclock.view", "timeclock.manual"],
    },
    "Auditor": {"description": "Solo lectura, incluida la bitácora.", "permissions": _all_view()},
}
