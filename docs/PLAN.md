# Plan maestro — SaaS de gestión para empresas constructoras

> Estado: borrador v0.2 (2026-11-21). Documento vivo: se actualiza al cerrar cada fase.
> Cambios v0.2: legislación de **Panamá**, Convención Colectiva SUNTRACS–CAPAC, marcaciones
> (reloj / archivo / manual), vacaciones, décimo tercer mes y comprobante de pago por empleado.

## 1. Visión

Plataforma SaaS multiempresa para administrar todas las áreas de una constructora que ejecuta
múltiples proyectos en paralelo. **Mercado inicial: Panamá.** El núcleo de planilla es
agnóstico del país; la legislación panameña vive en un paquete aparte (`payroll_pa`) para poder
agregar otros países después.

| Fase | Alcance | Objetivo |
|------|---------|----------|
| **0** | Fundaciones | Repo, CI/CD, multi-tenancy, login, roles, auditoría, shell de UI |
| **1** | **Planilla Panamá** | Marcaciones, jornadas, planilla por proyecto + oficina central → planilla global, vacaciones, décimo, comprobantes |
| 2 | Contabilidad base | Catálogo de cuentas, asientos, períodos, contabilización automática de planilla |
| 3 | Finanzas | Cuentas por pagar/cobrar, bancos, conciliación, facturación electrónica |
| 4 | Operaciones | Presupuestos de obra, compras, bodega/inventario, avance de obra, maquinaria |
| 5 | Extensiones | Portal del empleado, app móvil de marcación con GPS, conexión directa a relojes, BI, suscripciones SaaS |

La regla de oro: **la Fase 1 se diseña para que la Fase 2 la consuma sin rehacer nada**.

---

## 2. Arquitectura

### 2.1 Estilo: monolito modular
Un solo backend Django dividido en módulos (apps) con fronteras claras. Es lo correcto para
un equipo pequeño: un solo despliegue, transacciones ACID entre módulos, y si algún día un
módulo necesita escalar aparte, ya está aislado.

Reglas entre módulos:
- Un módulo **no** importa modelos internos de otro; usa su capa `services.py` / `selectors.py`.
- La comunicación "hacia adelante" (p. ej. planilla → contabilidad) se hace por **eventos de
  dominio** guardados en una tabla *outbox*, no con llamadas directas. Así la planilla funciona
  hoy sin contabilidad, y mañana la contabilidad se suscribe a `PayrollRunApproved`.

### 2.2 Multi-tenancy (SaaS)
**Decisión: base de datos compartida, esquema compartido, columna `tenant_id` en cada tabla
de negocio + Row-Level Security (RLS) de PostgreSQL.**

- Middleware resuelve el tenant (subdominio `empresa.app.com` o claim del token).
- `TenantAwareModel` (modelo base abstracto) + manager que filtra por tenant automáticamente.
- RLS en Postgres como segunda barrera: aunque un query olvide filtrar, la BD no devuelve
  datos de otro tenant (`SET app.tenant_id = ...` por request).
- Alternativa descartada por ahora: un esquema por tenant (`django-tenants`). Más aislamiento,
  pero migraciones lentas con cientos de clientes y reportes cruzados complejos.

### 2.3 Stack

**Backend**
- Python 3.12, Django 5.2 LTS, Django REST Framework (dependencias con `uv`)
- `drf-spectacular` (OpenAPI 3) → contrato de API que genera el cliente TypeScript
- `djangorestframework-simplejwt` (access token corto + refresh en cookie httpOnly)
- `django-filter`, `django-environ`, `django-storages` (S3)
- Celery + Redis: importación de marcaciones, cálculo de jornadas y planilla, PDFs/Excel, correos
- ReportLab (comprobantes de pago en PDF; Python puro, sin dependencias del sistema), openpyxl (importes/exportes Excel)
- Calidad: pytest + pytest-django + factory_boy + hypothesis, ruff, mypy (django-stubs), pre-commit

**Frontend**
- React 19 + TypeScript + Vite
- Tailwind CSS + **shadcn/ui** (Radix) → componentes accesibles y de aspecto profesional
- TanStack Query (estado servidor), TanStack Table (tablas grandes de planilla y marcaciones)
- React Hook Form + Zod (formularios y validación)
- React Router, i18n (`react-i18next`, español primero), Recharts para gráficos
- Cliente API generado desde OpenAPI (`orval`) → tipos siempre sincronizados con el backend
- Calidad: Vitest + Testing Library, Playwright (E2E), oxlint, Prettier

**Datos e infraestructura**
- PostgreSQL 16, Redis 7
- Docker / docker-compose para desarrollo local
- Nube recomendada: **AWS** — ECS Fargate (API + workers), RDS Postgres, ElastiCache Redis,
  S3 + CloudFront (frontend y archivos), Secrets Manager, CloudWatch
- Infraestructura como código: Terraform
- Observabilidad: Sentry (errores front y back), logs estructurados JSON

### 2.4 Estructura del repositorio (monorepo)

```
/
├── backend/
│   ├── config/               # settings (base/dev/test/prod), urls, celery
│   └── apps/
│       ├── core/             # modelos base, tenant, auditoría, eventos/outbox, utilidades
│       ├── accounts/         # usuarios, autenticación, roles y permisos
│       ├── organization/     # empresa, sucursales, centros de costo, catálogos generales
│       ├── projects/         # proyectos (obras), fases, asignación de personal
│       ├── hr/               # empleados, puestos, contratos, documentos
│       ├── timeclock/        # marcaciones de entrada/salida, relojes, horarios, motor de jornada
│       │   ├── importers/    #   zkteco, csv_generic, excel
│       │   └── engine/       #   emparejado de marcaciones y clasificación de horas
│       ├── attendance/       # horas aprobadas por proyecto (TimeEntry) que consume la planilla
│       ├── leave/            # vacaciones, licencias, incapacidades
│       ├── payroll/          # núcleo agnóstico: períodos, conceptos, corridas, comprobantes
│       ├── payroll_pa/       # legislación de Panamá: CSS, SE, ISR, décimo, convención, reportes
│       └── accounting/       # (Fase 2) — se crea vacío con sus interfaces
├── frontend/
│   └── src/{app,components/ui,features/<modulo>,lib,api}
├── infra/terraform/
├── docs/
└── .github/workflows/
```

---

## 3. Fundaciones transversales (Fase 0)

### 3.1 Autenticación
- Login email + contraseña, recuperación por correo, bloqueo por intentos fallidos.
- MFA (TOTP) opcional por usuario, obligatorio configurable por empresa.
- Un usuario puede pertenecer a varias empresas (contadores externos) → selector de empresa.

### 3.2 Roles y permisos (RBAC con alcance)
Permisos granulares (`payroll.run.approve`, `hr.employee.view_salary`, `timeclock.punch.manual`, …)
agrupados en roles. Cada asignación de rol tiene **alcance**: toda la empresa o proyectos específicos.

| Rol | Alcance típico | Puede |
|-----|----------------|-------|
| Super admin plataforma | Global SaaS | Gestionar tenants, planes, soporte |
| Administrador de empresa | Empresa | Todo dentro de su empresa, usuarios y roles |
| Gerente general | Empresa | Ver todo, aprobar planilla global |
| Recursos humanos | Empresa | Empleados, contratos, vacaciones, altas/bajas |
| Planillero | Empresa / proyectos | Importar marcaciones, calcular y preparar planillas |
| Contador | Empresa | Ver planilla, reportes legales, contabilizar (Fase 2) |
| Jefe de proyecto / Ing. residente | Proyecto | Ver personal y costo de su obra, aprobar jornadas y vacaciones |
| Supervisor / Maestro de obras | Proyecto | Registrar marcaciones manuales y corregir inconsistencias |
| Auditor / Consulta | Empresa | Solo lectura |
| Empleado (Fase 5) | Propio | Ver sus comprobantes y saldo de vacaciones |

Los roles son plantillas editables por cada empresa (pueden crear roles propios).

### 3.3 Auditoría y trazabilidad
- Bitácora de cambios (quién, cuándo, antes/después) en todo modelo sensible.
- Datos financieros y marcaciones **nunca se borran**: borrado lógico, correcciones como
  registros nuevos y documentos cerrados inmutables.

### 3.4 Convenciones de datos (críticas para la contabilidad futura)
- Montos: `Decimal(18,2)` (tasas `Decimal(9,6)`), **nunca float**. Siempre con `currency`
  (moneda funcional por defecto: USD/Balboa).
- Soporte multimoneda desde el día 1 (moneda funcional de la empresa + tipo de cambio).
- Toda transacción económica lleva: `tenant`, `fecha`, `período`, `centro_de_costo`, `proyecto`.
- PK UUID (no expone conteos entre tenants), `created_at/updated_at/created_by`.
- Fechas y horas con zona horaria (`America/Panama`) — esencial para marcaciones nocturnas.

### 3.5 UI shell
Layout con sidebar por módulos, selector de empresa y proyecto, buscador global, modo
claro/oscuro, tablas con filtros/exportación, diseño responsive. Sistema de diseño propio
(tokens de color, tipografía) sobre shadcn/ui para identidad de marca vendible.

---

## 4. Fase 1 — Planilla Panamá (detalle)

### 4.1 Flujo de punta a punta

```
Reloj biométrico ─┐
Excel / CSV ──────┼─► Punch (marcación cruda) ─► Motor de jornada ─► WorkDay ─► Aprobación ─► TimeEntry
Captura manual ───┘                                  (horario, feriados,       (jefe de     (horas por
                                                      jornada legal)            proyecto)    proyecto)
                                                                                                │
Contratos + tarifas convención + vacaciones + préstamos/embargos ──────────────────────────────►┤
                                                                                                ▼
                                    PayrollRun (regular | décimo | vacaciones | liquidación)
                                                                                                │
                         ┌──────────────────────┬───────────────────────┬──────────────────────┤
                         ▼                      ▼                       ▼                      ▼
                 Comprobante PDF         Archivo ACH banco       SIPE / DGI / SE      Evento PayrollRunApproved
                 por empleado                                                          (→ contabilidad, Fase 2)
```

### 4.2 Modelo de dominio

```
Tenant (empresa cliente SaaS)
 ├── CostCenter (árbol: Oficina central, Proyecto X, Proyecto X › Estructura…)
 ├── Project ──1:1── CostCenter
 ├── Position (puesto) ── CBACategory (categoría de la convención, opcional)
 ├── Employee (cédula, nº seguro social, banco/cuenta, fecha de ingreso)
 │    ├── EmploymentContract (tipo: indefinido | definido | obra determinada;
 │    │                       salario o tarifa por hora, frecuencia de pago, aplica convención)
 │    └── ProjectAssignment (empleado ↔ proyecto, desde/hasta, puesto)
 │
 ├── timeclock
 │    ├── Device (reloj; pertenece a proyecto u oficina) + EmployeeDeviceId (código en el reloj)
 │    ├── ImportBatch (archivo, origen, plantilla de mapeo, resultado, errores)
 │    ├── Punch (empleado, timestamp, tipo entrada/salida/desconocido, origen
 │    │          reloj|archivo|manual|app, dispositivo, lote, hash anti-duplicado,
 │    │          corrige_a → Punch, motivo, usuario)
 │    ├── Shift / ShiftAssignment (horario, tolerancias, redondeo, almuerzo, cruza medianoche)
 │    ├── HolidayCalendar (feriados nacionales por año)
 │    └── WorkDay (horas ordinarias, extras diurnas/nocturnas/mixtas, domingo, feriado,
 │                 tardanza, ausencia, inconsistencias, estado)
 │
 ├── attendance.TimeEntry (horas aprobadas: empleado, fecha, proyecto, tipo de hora)
 │
 ├── leave
 │    ├── VacationBalance (días ganados, tomados, pagados, vencidos)
 │    ├── VacationRequest (fechas, días, estado, pagar en planilla | corrida propia)
 │    └── LeaveRecord (incapacidades CSS, licencias, permisos)
 │
 ├── payroll
 │    ├── LegalParameter (clave, valor, vigente_desde/hasta, país) — tasas y topes
 │    ├── CBAWageTable (tarifa por hora por categoría de convención, con vigencia)
 │    ├── PayrollConcept (ingreso | deducción | aporte patronal | provisión;
 │    │                   fórmula, base, gravable CSS/SE/ISR, prioridad, cuenta contable)
 │    ├── EmployeeRecurringItem (préstamos, embargos, pensión alimenticia, cuota sindical)
 │    ├── PayrollCalendar / PayrollPeriod (semanal, quincenal, mensual)
 │    ├── PayrollRun
 │    │    ├── tipo: regular | décimo | vacaciones | liquidación
 │    │    ├── alcance: proyecto | oficina central | global
 │    │    ├── estado: borrador → calculada → revisada → aprobada → pagada → contabilizada
 │    │    └── PayrollLine (empleado) → PayrollLineItem (concepto, cantidad, monto, centro de costo)
 │    └── Payslip (comprobante: número correlativo, PDF en S3, enviado, reemplaza_a → Payslip)
```

Puntos clave de diseño:
- **Oficina central es un centro de costo más**, no un caso especial. La planilla global es la
  consolidación de todas las corridas del período.
- Un empleado puede rotar entre proyectos en un mismo período: sus horas (`TimeEntry`)
  determinan cómo se **distribuye su costo** entre centros de costo. Cada `PayrollLineItem`
  queda asignado a un centro de costo → esto es exactamente lo que la contabilidad necesitará.
- **Motor de reglas por país**: el núcleo `payroll` no conoce leyes; `payroll_pa` registra los
  conceptos, fórmulas, parámetros y reportes de Panamá. Los parámetros son datos versionados por
  fecha, no código: cuando cambie una tasa, se carga una nueva vigencia sin desplegar.
- Una planilla aprobada es inmutable; correcciones se hacen con ajustes en el período siguiente.
- Se guarda la **base de cálculo** de cada línea (horas, tarifa, promedio usado) para poder
  explicar cualquier monto ante el empleado, MITRADEL o la CSS.

### 4.3 Marcaciones de entrada y salida (`timeclock`)

**Fuentes de marcación**
1. **Reloj biométrico (ZKTeco u otros):** importación del archivo exportado por el equipo
   (`attlog`/CSV/TXT). Fase 5: conexión directa (ZKTeco push/ADMS) para recibir marcaciones en
   tiempo casi real.
2. **Excel / CSV de otro sistema:** importador genérico con **plantillas de mapeo de columnas**
   guardadas por empresa (columna de código de empleado, fecha, hora, tipo, dispositivo).
3. **Captura manual:** para obras sin reloj. El supervisor registra marcaciones por cuadrilla o
   en lote (misma hora a varios empleados). Toda marcación manual queda identificada como tal y
   requiere permiso específico.
4. **App móvil con GPS y foto (Fase 5).**

**Proceso de importación**
- Subir archivo → validación en segundo plano (Celery) → **vista previa** con filas válidas,
  errores (empleado no encontrado, fecha inválida) y duplicados detectados por hash →
  confirmar → se crean los `Punch` del lote. Un lote puede revertirse completo si se importó mal.

**Motor de jornada**
- Empareja entradas y salidas según el horario asignado, incluyendo turnos que cruzan la
  medianoche y marcaciones sin tipo (se infiere por secuencia).
- Aplica tolerancia de llegada, redondeo y descuento de almuerzo.
- Clasifica cada hora según la **jornada legal panameña** (diurna, nocturna, mixta), y separa
  horas ordinarias, extras, domingo/descanso y feriado.
- Detecta inconsistencias: marcación impar, falta de salida, jornada excesiva, marcación en
  proyecto no asignado.

**Bandeja de excepciones y aprobación**
- El supervisor corrige (creando un `Punch` de corrección con motivo; el original se conserva).
- El jefe de proyecto aprueba las jornadas del período; al aprobar se generan los `TimeEntry`
  por proyecto. La planilla solo usa horas aprobadas.

### 4.4 Legislación laboral de Panamá (`payroll_pa`)

> ⚠️ Todos los porcentajes, topes y tablas se cargan como `LegalParameter` con vigencia por
> fecha, **no se escriben en el código**. La Ley 462 de 2025 (reforma de la CSS) aumenta la
> cuota patronal de forma escalonada. Cada valor debe validarlo un contador o abogado laboral
> panameño antes de producción. Los valores de abajo son la referencia inicial.

**Jornadas (Código de Trabajo)**
| Jornada | Horario | Máximo diario | Máximo semanal |
|---------|---------|---------------|----------------|
| Diurna | 6:00 – 18:00 | 8 h | 48 h |
| Nocturna | 18:00 – 6:00 | 7 h | 42 h |
| Mixta | abarca ambos (≤ 3 h nocturnas) | 7.5 h | 45 h |

**Recargos**
- Horas extra: +25% diurna, +50% nocturna, +75% mixta que se prolonga en la noche.
- Horas extra que excedan los límites legales: recargo adicional configurable.
- Domingo o día de descanso trabajado: +50%.
- Feriado nacional trabajado: +150% (además del salario del día).

**Feriados nacionales** (calendario anual configurable): 1 y 9 de enero, martes de carnaval,
Viernes Santo, 1 de mayo, 3, 5, 10 y 28 de noviembre, 8, 20 y 25 de diciembre. Se pueden
agregar días de duelo o decretados.

**Deducciones del empleado**
- Seguro Social (CSS): 9.75%.
- Seguro Educativo: 1.25%.
- Impuesto sobre la Renta (ISR), tabla anual: hasta B/.11,000 exento; de 11,000 a 50,000 → 15%
  sobre el excedente; más de 50,000 → B/.5,850 + 25% sobre el excedente. La retención por período
  se calcula proyectando el ingreso anual (13 meses, incluyendo décimo).
- Otras deducciones con **prioridad legal**: pensión alimenticia, embargos judiciales,
  préstamos (con límite de descuento), cuota sindical, descuentos autorizados.

**Aportes patronales**
- Seguro Social (CSS): 12.25% + incremento escalonado de la Ley 462.
- Seguro Educativo: 1.50%.
- Riesgos Profesionales: tasa según la actividad (alta en construcción), configurable por empresa.

**Décimo tercer mes**
- Tres partidas: 15 de abril, 15 de agosto y 15 de diciembre.
- Cada partida = 1/12 de lo devengado en el cuatrimestre correspondiente.
- CSS especial: 7.25% empleado, 10.75% patrono. No paga Seguro Educativo. ISR según tabla.
- Se calcula como **corrida especial** (`tipo = décimo`) y se acumula mensualmente como provisión.

**Vacaciones** (`leave`)
- 30 días de vacaciones por cada 11 meses de trabajo continuo; el saldo se acumula de forma
  proporcional (1 día por cada 11 días trabajados).
- Pago = promedio de lo devengado en los últimos 11 meses (incluye extras, recargos y
  comisiones), según la base configurada.
- Pagan CSS y Seguro Educativo normales y forman parte de la base del décimo.
- Funcionalidades: saldo por empleado, solicitud y aprobación, programación anual, pago en la
  planilla regular o como corrida propia (`tipo = vacaciones`), control de vacaciones vencidas,
  pago proporcional en liquidación, **provisión mensual** para la contabilidad.

**Convención Colectiva SUNTRACS–CAPAC** (paquete activable por empresa)
- Tabla de **tarifas por hora por categoría** (ayudante, albañil, armador, carpintero,
  soldador, operador de equipo, etc.) con vigencia por fecha (`CBAWageTable`).
- Pago **semanal** para el personal de obra.
- Bonificaciones y beneficios de la convención (herramientas, transporte, trabajo en altura,
  etc.) como conceptos configurables.
- Validación: el sistema alerta si un contrato tiene tarifa inferior a la de su categoría.

**Terminación laboral / liquidación** (`tipo = liquidación`)
- Prima de antigüedad: una semana de salario por cada año trabajado (proporcional).
- Indemnización (art. 225 del Código de Trabajo) cuando el despido es injustificado.
- Vacaciones proporcionales y vencidas, décimo proporcional y salarios pendientes.
- **Fondo de Cesantía** (Ley 44 de 1995): provisión mensual y aporte trimestral del patrono.
- Terminación por fin de obra o de etapa (contratos por obra determinada) con su cálculo propio.

**Frecuencias de pago**
- Semanal en obra, quincenal o mensual en oficina. Una empresa puede tener varios calendarios.

**Reportes legales y archivos**
- Archivo mensual para el **SIPE de la CSS**.
- Planilla de Seguro Educativo.
- Retenciones de ISR mensuales y **Planilla 03 de la DGI** (anual), certificado de retenciones.
- Reportes a MITRADEL cuando corresponda.
- Archivo de pago **ACH** con formato por banco (Banco General, Banistmo, BAC, etc.).

### 4.5 Comprobante de pago
- Se genera **uno por empleado en cada corrida** (regular, décimo, vacaciones, liquidación),
  en PDF (ReportLab).
- Contenido:
  - Datos de la empresa (nombre, RUC) y del empleado (nombre, cédula, nº de seguro social, puesto).
  - Período de pago, fecha de pago y proyecto(s) / centro de costo.
  - Detalle de horas: ordinarias, extras por tipo, domingo, feriado, con tarifa y recargo.
  - Ingresos, deducciones (CSS, SE, ISR, préstamos, etc.) y **neto a pagar**.
  - Acumulados del año: devengado, ISR retenido, décimo acumulado, saldo de vacaciones.
- Numeración correlativa e inmutable; una corrección emite un comprobante nuevo que referencia
  al anterior.
- Envío masivo por correo, almacenamiento en S3, descarga desde el expediente del empleado.
- Fase 5: portal del empleado con acuse de recibo digital.

### 4.6 Funcionalidades de la Fase 1
1. Catálogos: puestos, categorías de convención, centros de costo, proyectos, bancos, tipos de contrato, feriados.
2. Expediente de empleado: datos personales, documentos, contrato, historial salarial, cuenta bancaria.
3. Asignación de personal a proyectos.
4. **Marcaciones:** importación desde reloj y Excel/CSV, captura manual, lotes y reversión.
5. **Horarios y motor de jornada**, bandeja de excepciones, aprobación por proyecto.
6. Conceptos de planilla configurables y parámetros legales de Panamá con vigencia.
7. Préstamos, embargos, pensiones alimenticias y descuentos recurrentes.
8. Cálculo de planilla por proyecto y oficina central (asíncrono con Celery).
9. Flujo de revisión y aprobación; planilla global consolidada.
10. **Comprobantes de pago** PDF por empleado y envío por correo.
11. Archivo ACH y reportes legales (SIPE, Seguro Educativo, ISR, Planilla 03).
12. **Vacaciones:** saldos, solicitudes, pago y provisión.
13. **Décimo tercer mes:** provisión y corridas de abril, agosto y diciembre.
14. Liquidaciones, prima de antigüedad y Fondo de Cesantía.
15. Reportes de gestión: costo de mano de obra por obra, horas extra por proyecto, comparativos entre períodos.

### 4.7 Preparación para contabilidad (sin construirla aún)
- Cada `PayrollConcept` tiene campos de **mapeo contable** (cuenta débito/crédito) que por ahora
  son texto/código; en Fase 2 se convierten en FK al catálogo de cuentas.
- **Provisiones** como conceptos propios con su mapeo: décimo tercer mes, vacaciones, prima de
  antigüedad, Fondo de Cesantía, Riesgos Profesionales.
- Al aprobar una corrida se emite el evento `PayrollRunApproved` en la outbox con el resumen por
  concepto × centro de costo, incluyendo las cuotas patronales. En Fase 2, `accounting` lo consume
  y genera el asiento (gasto de planilla por obra, pasivos con CSS, DGI, empleados).
- Estado `contabilizada` ya existe en el flujo, aunque en Fase 1 no se use.
- `CostCenter` y `Project` viven en `organization`/`projects`, no en `payroll`, porque los
  usarán compras, inventario y contabilidad.

---

## 5. CI/CD con GitHub Actions

Ramas: `main` (siempre desplegable) + ramas de feature con Pull Request obligatorio.

| Workflow | Disparador | Pasos |
|----------|-----------|-------|
| `ci-backend.yml` | PR / push que toque `backend/` | ruff, mypy, pytest con Postgres de servicio, cobertura, `makemigrations --check` |
| `ci-frontend.yml` | PR / push que toque `frontend/` | lint, typecheck, Vitest, build |
| `e2e.yml` | PR a `main` | docker-compose completo + Playwright |
| `deploy-staging.yml` | merge a `main` | build de imágenes → ECR, migraciones, deploy ECS, frontend a S3 + invalidación CloudFront |
| `deploy-production.yml` | tag `v*` + aprobación manual (GitHub Environments) | mismo pipeline sobre producción |
| `security.yml` | semanal / PR | Dependabot, `pip-audit`, `npm audit`, CodeQL, escaneo de imagen (Trivy) |

- Autenticación con AWS por **OIDC** (sin llaves de larga duración en GitHub).
- Secretos por ambiente en GitHub Environments + AWS Secrets Manager.
- Ambientes: `local` → `staging` → `production`. Migraciones de BD compatibles hacia atrás
  (expand/contract) para desplegar sin downtime.

### 5.1 Estrategia de pruebas de planilla
- **Casos de referencia (golden tests)** validados por un contador panameño, guardados como
  fixtures: semana de obra con extras nocturnas y feriado, quincena de oficina, décimo,
  vacaciones, liquidación por despido injustificado y por fin de obra.
- Todos los cálculos con `Decimal` y reglas de redondeo explícitas.
- Pruebas de propiedades (hypothesis) del motor de jornada: turnos que cruzan la medianoche,
  marcaciones impares, duplicados, cambios de horario a mitad de semana.
- Pruebas de los importadores con archivos reales de muestra (ZKTeco y Excel).

---

## 6. Hoja de ruta Fase 0 + Fase 1 (sprints de 2 semanas)

| Sprint | Entregable |
|--------|-----------|
| 1 ✅ | Monorepo, docker-compose, Django + React base, CI (lint/tests), pre-commit |
| 2 ✅ | Tenancy + RLS, usuarios, login JWT, recuperación de contraseña, UI shell y sistema de diseño |
| 3 ✅ | Roles y permisos, auditoría inalterable, administración de usuarios e invitaciones, MFA (TOTP), cliente API generado con orval. *Infraestructura pospuesta (ver 3b).* |
| 3b | Terraform + despliegue continuo a staging — pendiente de elegir proveedor de nube |
| 4 ✅ | Organización: centros de costo, proyectos, puestos, categorías y tarifas de convención, feriados de Panamá; alcance de roles por proyecto |
| 5 ✅ | Expediente de empleados, contratos con historial salarial, asignación a proyectos, documentos |
| 6 ✅ | **Marcaciones:** modelos, dispositivos, importadores ZKTeco y Excel/CSV, captura manual, lotes |
| 7 ✅ | **Horarios y motor de jornada**, bandeja de excepciones, aprobación → TimeEntry |
| 8 ✅ | Motor de planilla, `payroll_pa`, parámetros legales con vigencia, tarifas de convención, descuentos |
| 9 ✅ | Corridas de planilla, flujo de aprobación, planilla global consolidada |
| 10 ✅ | **Comprobantes de pago**, archivo ACH, SIPE y Seguro Educativo |
| 11 | **Vacaciones** y **décimo tercer mes** (provisiones y corridas especiales) |
| 12 | Liquidaciones, Fondo de Cesantía, reportes DGI, endurecimiento, deploy a producción, piloto con cliente |

---

## 7. Decisiones

### Resueltas
- País inicial: **Panamá**.
- Personal de obra bajo la **Convención Colectiva SUNTRACS–CAPAC**, pago semanal.
- Fuentes de marcación: **reloj biométrico (ZKTeco u otros), Excel/CSV de otros sistemas y
  captura manual** (para clientes sin sistema).

### Pendientes
1. **Validación legal**: revisar con un contador o abogado laboral panameño las tasas vigentes
   (Ley 462 de 2025), la tarifa de Riesgos Profesionales y la tabla de la convención actual.
2. **Proveedor de nube** (AWS recomendado; alternativas más simples: DigitalOcean, Render).
3. **Bancos** para el archivo ACH y sus formatos.
4. **Modelo exacto del reloj** y muestra de archivo exportado para construir el importador.
5. ¿El comprobante debe mostrar también los **aportes patronales**?
6. **Facturación electrónica** de la DGI (afecta Fase 3).
7. **Modelo comercial SaaS**: planes por número de empleados/proyectos → define límites y
   módulo de suscripción (Stripe u otro).
