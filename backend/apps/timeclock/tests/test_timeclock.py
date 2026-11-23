import io
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import InternalError, ProgrammingError, transaction
from django.urls import reverse

from apps.core.tenancy import tenant_context
from apps.hr.models import ProjectAssignment
from apps.hr.services import create_employee
from apps.iam.services import set_member_assignments
from apps.organization.services import bootstrap_organization
from apps.projects.services import create_project
from apps.tenants.models import Membership
from apps.timeclock.importers import tabular, zkteco
from apps.timeclock.importers.base import ImportFileError
from apps.timeclock.models import ClockCode, Device, ImportTemplate, Punch
from conftest import client_for, make_member

pytestmark = pytest.mark.django_db
PA = ZoneInfo("America/Panama")

ATTLOG = (
    "        1\t2026-11-16 06:58:12\t1\t0\t1\t0\n"
    "        1\t2026-11-16 15:02:40\t1\t1\t1\t0\n"
    "     0002\t2026-11-16 07:01:00\t1\t0\t1\t0\n"
    "        1\t2026-11-16 06:58:12\t1\t0\t1\t0\n"  # repetida
    "       99\t2026-11-16 07:00:00\t1\t0\t1\t0\n"  # código sin empleado
    "        3\t2025-01-01 07:00:00\t1\t0\t1\t0\n"  # antes del ingreso
    "basura sin formato\n"
)


def employee(code, id_number, hire=date(2026, 1, 5)):
    return create_employee(
        code=code,
        first_name=code,
        last_name="Prueba",
        id_number=id_number,
        hire_date=hire,
        payment_method="cash",
    )


@pytest.fixture
def setup(tenant):
    bootstrap_organization(tenant, years=())
    with tenant_context(tenant):
        p1 = create_project(code="P-1", name="Torre", status="active")
        p2 = create_project(code="P-2", name="Puente", status="active")
        e1, e2, e3 = employee("E-1", "8-1-1"), employee("E-2", "8-2-2"), employee("E-3", "8-3-3")
        for e in (e1, e2, e3):
            ProjectAssignment.objects.create(employee=e, project=p1, start_date=date(2026, 1, 5))
        device = Device.objects.create(name="Reloj Torre", serial_number="ZK123", project=p1)
        ClockCode.objects.create(employee=e1, code="1")
        ClockCode.objects.create(employee=e2, code="2")
        ClockCode.objects.create(employee=e3, code="3", device=device)
    return {"p1": p1, "p2": p2, "e1": e1, "e2": e2, "e3": e3, "device": device}


def upload(api, data, name="attlog.dat", **extra):
    return api.post(
        reverse("import-batch-list"),
        {"file": SimpleUploadedFile(name, data), **extra},
        format="multipart",
    )


class TestParsers:
    def test_zkteco_lines(self):
        rows = zkteco.parse(ATTLOG.encode())
        assert rows[0].code == "1" and rows[0].direction == "in"
        assert rows[0].timestamp == datetime(2026, 11, 16, 6, 58, 12)
        assert rows[1].direction == "out"
        assert rows[-1].error

    def test_zkteco_rejects_other_formats(self):
        with pytest.raises(ImportFileError):
            zkteco.parse(b"codigo;fecha\nA;B\n")

    def test_csv_with_template(self):
        template = ImportTemplate(
            name="t",
            employee_column="Cedula",
            employee_key="id_number",
            date_column="Fecha",
            time_column="Hora",
            direction_column="Tipo",
        )
        data = (
            "Cedula;Fecha;Hora;Tipo\n8-1-1;16/11/2026;7:05;E\n8-1-1;16/11/2026;3:30 PM;S\n;x;y;z\n"
        )
        rows = tabular.parse(data.encode("cp1252"), "export.csv", template)
        assert [r.direction for r in rows] == ["in", "out", "unknown"]
        assert rows[1].timestamp == datetime(2026, 11, 16, 15, 30)
        assert rows[2].error == "Falta el empleado."

    def test_xlsx_with_combined_datetime(self):
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.append(["ID", "Marcación"])
        ws.append([12.0, datetime(2026, 11, 16, 7, 0)])
        buffer = io.BytesIO()
        wb.save(buffer)
        template = ImportTemplate(name="x", employee_column="1", datetime_column="Marcación")
        rows = tabular.parse(buffer.getvalue(), "export.xlsx", template)
        assert rows[0].code == "12" and rows[0].timestamp == datetime(2026, 11, 16, 7, 0)

    def test_missing_column_is_reported(self):
        template = ImportTemplate(name="x", employee_column="Empleado", datetime_column="Fecha")
        with pytest.raises(ImportFileError, match="Empleado"):
            tabular.parse(b"A,B\n1,2\n", "x.csv", template)


class TestImport:
    def test_preview_confirm_reimport_and_revert(
        self, owner_api, tenant, setup, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            response = upload(
                owner_api, ATTLOG.encode(), source="zkteco", device=str(setup["device"].pk)
            )
        assert response.status_code == 201, response.json()
        batch_url = reverse("import-batch-detail", args=[response.json()["id"]])
        batch = owner_api.get(batch_url).json()
        assert batch["status"] == "preview"
        assert (batch["total_rows"], batch["valid_rows"]) == (7, 3)
        assert (batch["error_rows"], batch["duplicate_rows"]) == (3, 1)

        rows = owner_api.get(f"{batch_url}rows/", {"row_status": "error"}).json()["results"]
        messages = {r["raw_code"]: r["message"] for r in rows}
        assert "sin empleado" in messages["99"]
        assert "ingreso" in messages["3"]

        confirmed = owner_api.post(f"{batch_url}confirm/").json()
        assert confirmed["status"] == "confirmed" and confirmed["punch_count"] == 3
        with tenant_context(tenant):
            punch = Punch.objects.get(employee=setup["e1"], direction="in")
            assert punch.project == setup["p1"] and punch.source == "device"
            assert punch.timestamp == datetime(2026, 11, 16, 6, 58, 12, tzinfo=PA)

        # Reimportar el mismo archivo: todo queda como duplicado.
        with django_capture_on_commit_callbacks(execute=True):
            again = upload(
                owner_api, ATTLOG.encode(), source="zkteco", device=str(setup["device"].pk)
            )
        again_body = owner_api.get(reverse("import-batch-detail", args=[again.json()["id"]])).json()
        assert again_body["valid_rows"] == 0 and again_body["duplicate_rows"] == 4

        reverted = owner_api.post(
            f"{batch_url}revert/", {"reason": "Archivo equivocado"}, format="json"
        )
        assert reverted.json()["status"] == "reverted" and reverted.json()["punch_count"] == 0
        assert owner_api.get(reverse("punch-list")).json()["count"] == 0
        voided = owner_api.get(reverse("punch-list"), {"include_void": "true"}).json()
        assert voided["count"] == 3 and all(p["is_void"] for p in voided["results"])

    def test_template_import_uses_device_column(
        self, owner_api, tenant, setup, django_capture_on_commit_callbacks
    ):
        template = owner_api.post(
            reverse("import-template-list"),
            {
                "name": "Sistema anterior",
                "employee_key": "employee_code",
                "employee_column": "Empleado",
                "datetime_column": "Fecha hora",
                "date_format": "%Y-%m-%d",
                "time_format": "%H:%M",
                "device_column": "Reloj",
            },
            format="json",
        )
        assert template.status_code == 201, template.json()
        csv_data = (
            b"Empleado,Fecha hora,Reloj\nE-2,2026-11-17 07:00,ZK123\nE-2,2026-11-17 16:00,OTRO\n"
        )
        with django_capture_on_commit_callbacks(execute=True):
            response = upload(
                owner_api, csv_data, "datos.csv", source="template", template=template.json()["id"]
            )
        url = reverse("import-batch-detail", args=[response.json()["id"]])
        body = owner_api.get(url).json()
        assert (body["valid_rows"], body["error_rows"]) == (1, 1)
        owner_api.post(f"{url}confirm/")
        with tenant_context(tenant):
            assert Punch.objects.get().project == setup["p1"]

    def test_unreadable_file_fails_with_message(
        self, owner_api, setup, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            response = upload(
                owner_api, b"hola\nmundo\n", source="zkteco", device=str(setup["device"].pk)
            )
        body = owner_api.get(reverse("import-batch-detail", args=[response.json()["id"]])).json()
        assert body["status"] == "failed" and "ZKTeco" in body["error"]

    def test_validation(self, owner_api, setup):
        assert upload(owner_api, b"x", source="zkteco").status_code == 400  # sin reloj
        bad_ext = upload(owner_api, b"x", "a.exe", source="zkteco", device=str(setup["device"].pk))
        assert bad_ext.status_code == 400

    def test_clock_code_clash_after_normalization(self, owner_api, setup):
        response = owner_api.post(
            reverse("clock-code-list"),
            {"employee": str(setup["e2"].pk), "code": "0001"},
            format="json",
        )
        assert response.status_code == 400
        assert "ya está asignado" in response.json()["code"][0]


class TestManualAndCorrections:
    def test_crew_entry_skips_existing(self, owner_api, tenant, setup):
        url = reverse("punch-manual")
        payload = {
            "employees": [str(setup["e1"].pk), str(setup["e2"].pk)],
            "date": "2026-11-18",
            "time": "07:00",
            "direction": "in",
            "project": str(setup["p1"].pk),
            "reason": "Obra sin reloj",
        }
        first = owner_api.post(url, payload, format="json")
        assert first.status_code == 201, first.json()
        assert len(first.json()["created"]) == 2
        again = owner_api.post(
            url, {**payload, "employees": [str(setup["e1"].pk), str(setup["e3"].pk)]}, format="json"
        )
        assert len(again.json()["created"]) == 1
        assert again.json()["skipped"] == [setup["e1"].full_name]
        assert owner_api.post(url, {**payload, "reason": ""}, format="json").status_code == 400
        future = owner_api.post(url, {**payload, "date": "2099-01-01"}, format="json")
        assert future.status_code == 400

    def test_correct_and_void(self, owner_api, tenant, setup):
        created = owner_api.post(
            reverse("punch-manual"),
            {
                "employees": [str(setup["e1"].pk)],
                "date": "2026-11-18",
                "time": "07:00",
                "direction": "in",
                "project": str(setup["p1"].pk),
                "reason": "Sin reloj",
            },
            format="json",
        ).json()["created"][0]
        fixed = owner_api.post(
            reverse("punch-correct", args=[created["id"]]),
            {
                "date": "2026-11-18",
                "time": "06:45",
                "direction": "in",
                "reason": "Hora mal digitada",
            },
            format="json",
        )
        assert fixed.status_code == 201, fixed.json()
        assert fixed.json()["corrects"] == created["id"]
        with tenant_context(tenant):
            assert Punch.objects.get(pk=created["id"]).is_void
        again = owner_api.post(
            reverse("punch-void", args=[created["id"]]), {"reason": "x"}, format="json"
        )
        assert again.status_code == 400
        voided = owner_api.post(
            reverse("punch-void", args=[fixed.json()["id"]]),
            {"reason": "No trabajó"},
            format="json",
        )
        assert voided.json()["is_void"] is True and voided.json()["void_reason"] == "No trabajó"

    def test_database_forbids_editing_or_deleting(self, tenant, setup):
        with tenant_context(tenant):
            punch = Punch.objects.create(
                employee=setup["e1"],
                timestamp=datetime(2026, 11, 18, 7, tzinfo=PA),
                source="device",
            )
            for change in (
                lambda: Punch.objects.filter(pk=punch.pk).update(direction="out"),
                lambda: Punch.objects.filter(pk=punch.pk).delete(),
            ):
                with pytest.raises((InternalError, ProgrammingError)), transaction.atomic():
                    change()
            Punch.objects.filter(pk=punch.pk).update(is_void=True, void_reason="ok")
            with pytest.raises((InternalError, ProgrammingError)), transaction.atomic():
                Punch.objects.filter(pk=punch.pk).update(is_void=False)


class TestScope:
    @pytest.fixture
    def supervisor(self, tenant, roles, setup):
        user = make_member(tenant, "sup@obra.pa", [], roles)
        m = Membership.objects.get(user=user)
        with tenant_context(tenant):
            set_member_assignments(m, [(roles["Supervisor de obra"], [setup["p1"]])])
            other = employee("E-9", "8-9-9")
            ProjectAssignment.objects.create(
                employee=other, project=setup["p2"], start_date=date(2026, 1, 5)
            )
            for emp, project in ((setup["e1"], setup["p1"]), (other, setup["p2"])):
                Punch.objects.create(
                    employee=emp,
                    timestamp=datetime(2026, 11, 18, 7, tzinfo=PA),
                    source="device",
                    project=project,
                )
        return client_for(user, tenant), other

    def test_sees_only_own_project(self, supervisor):
        api, _ = supervisor
        rows = api.get(reverse("punch-list")).json()["results"]
        assert [r["project_code"] for r in rows] == ["P-1"]

    def test_manual_limited_to_project_and_assigned_staff(self, supervisor, setup):
        api, other = supervisor
        payload = {
            "employees": [str(setup["e2"].pk)],
            "date": "2026-11-18",
            "time": "16:00",
            "direction": "out",
            "project": str(setup["p1"].pk),
            "reason": "Cuadrilla sin reloj",
        }
        assert api.post(reverse("punch-manual"), payload, format="json").status_code == 201
        wrong_project = {**payload, "project": str(setup["p2"].pk)}
        assert api.post(reverse("punch-manual"), wrong_project, format="json").status_code == 403
        foreign = {**payload, "employees": [str(other.pk)]}
        assert api.post(reverse("punch-manual"), foreign, format="json").status_code == 400

    def test_cannot_import_without_permission(self, supervisor, setup):
        api, _ = supervisor
        response = upload(api, ATTLOG.encode(), source="zkteco", device=str(setup["device"].pk))
        assert response.status_code == 403
