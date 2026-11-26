import csv
import io
import zipfile
from datetime import date
from decimal import Decimal

import pytest
from django.core import mail
from django.urls import reverse

from apps.attendance.models import TimeEntry
from apps.core.tenancy import tenant_context
from apps.hr.models import ProjectAssignment
from apps.hr.services import create_contract, create_employee
from apps.organization.models import Position
from apps.organization.services import bootstrap_organization
from apps.payroll.models import PayrollSettings, Payslip
from apps.payroll.payslips import build_data
from apps.payroll.services import bootstrap_payroll
from apps.projects.services import create_project
from apps.timeclock.models import WorkDay
from apps.timeclock.services import bootstrap_timeclock
from conftest import client_for, make_member

pytestmark = pytest.mark.django_db
D = Decimal


@pytest.fixture
def setup(tenant):
    bootstrap_organization(tenant, years=(2026,))
    with tenant_context(tenant):
        bootstrap_timeclock()
        bootstrap_payroll()
        PayrollSettings.objects.update(
            ach_routes={"banco_general": "71"}, company_account_number="0301001"
        )
        project = create_project(code="P-1", name="Torre", status="active")
        alb = Position.objects.get(code="ALB")
        people = {}
        for code, cedula, method, email in (
            ("E-1", "8-1-1", "ach", "ana@correo.pa"),
            ("E-2", "8-2-2", "cash", ""),
        ):
            extra = (
                {"bank": "banco_general", "account_type": "savings", "account_number": "0401234567"}
                if method == "ach"
                else {}
            )
            e = create_employee(
                code=code,
                first_name=code,
                last_name="Obra",
                id_number=cedula,
                css_number="123",
                hire_date=date(2026, 1, 5),
                payment_method=method,
                email=email,
                **extra,
            )
            ProjectAssignment.objects.create(
                employee=e, project=project, start_date=date(2026, 1, 5)
            )
            create_contract(
                employee=e,
                contract_type="project",
                start_date=date(2026, 1, 5),
                position=alb,
                project=project,
                pay_frequency="weekly",
                pay_basis="hourly",
                initial_amount=D("5"),
                uses_cba_rate=False,
            )
            people[code] = e
    return {"project": project, **people}


def hours(employee, project, day, qty="40"):
    wd = WorkDay.objects.create(
        employee=employee, date=day, project=project, day_kind="regular", status="approved"
    )
    TimeEntry.objects.create(
        employee=employee,
        date=day,
        project=project,
        cost_center=project.cost_center,
        hour_type="ordinary",
        day_kind="regular",
        hours=D(qty),
        workday=wd,
    )


def approved_run(api, tenant, setup, start, end, pay, capture):
    with tenant_context(tenant):
        for code in ("E-1", "E-2"):
            hours(setup[code], setup["project"], date.fromisoformat(start))
    run = api.post(
        reverse("payroll-run-list"),
        {
            "frequency": "weekly",
            "scope": "project",
            "project": str(setup["project"].pk),
            "period_start": start,
            "period_end": end,
            "pay_date": pay,
        },
        format="json",
    ).json()
    api.post(reverse("payroll-run-calculate", args=[run["id"]]))
    with capture(execute=True):
        assert api.post(reverse("payroll-run-approve", args=[run["id"]])).status_code == 200
    return run["id"]


def test_payslips_issued_on_approval_with_correlative_numbers(
    owner_api, tenant, setup, django_capture_on_commit_callbacks
):
    run_id = approved_run(
        owner_api,
        tenant,
        setup,
        "2026-11-16",
        "2026-11-22",
        "2026-11-27",
        django_capture_on_commit_callbacks,
    )
    slips = owner_api.get(reverse("payroll-run-payslips", args=[run_id])).json()
    assert [s["number"] for s in slips] == [1, 2]
    assert (
        slips[0]["net"] == "177.29"
    )  # 200 - CSS 19.50 - SE 2.50 - ISR 0.71 (11,266.67 anual proyectado)
    # Idempotente: no repite números.
    again = owner_api.post(reverse("payroll-run-generate-payslips", args=[run_id])).json()
    assert again == {"created": 0}

    pdf = owner_api.get(reverse("payslip-download", args=[slips[0]["id"]]))
    content = b"".join(pdf.streaming_content)
    assert pdf["Content-Type"] == "application/pdf" and content.startswith(b"%PDF")

    archive = zipfile.ZipFile(
        io.BytesIO(owner_api.get(reverse("payroll-run-payslips-zip", args=[run_id])).content)
    )
    assert sorted(archive.namelist()) == ["0000001_E-1_Obra.pdf", "0000002_E-2_Obra.pdf"]

    sent = owner_api.post(reverse("payroll-run-email-payslips", args=[run_id])).json()
    assert sent == {"sent": 1, "missing_email": ["E-2 Obra"]}
    assert mail.outbox[0].to == ["ana@correo.pa"]
    assert mail.outbox[0].attachments[0][0] == "comprobante_0000001.pdf"

    by_employee = owner_api.get(reverse("payslip-list"), {"employee": str(setup["E-1"].pk)}).json()
    assert by_employee["count"] == 1 and by_employee["results"][0]["emailed_to"] == "ana@correo.pa"


def test_payslip_content_and_year_to_date(
    owner_api, tenant, setup, django_capture_on_commit_callbacks
):
    approved_run(
        owner_api,
        tenant,
        setup,
        "2026-11-16",
        "2026-11-22",
        "2026-11-27",
        django_capture_on_commit_callbacks,
    )
    second = approved_run(
        owner_api,
        tenant,
        setup,
        "2026-11-23",
        "2026-11-29",
        "2026-12-04",
        django_capture_on_commit_callbacks,
    )
    with tenant_context(tenant):
        slip = Payslip.objects.get(run_id=second, employee=setup["E-1"])
        data = build_data(slip.line, slip.number)
    assert data.payment == "ACH Banco General ****4567"
    assert data.cost_centers == "P-1"
    assert [(r.name, r.amount) for r in data.earnings] == [("Horas ordinarias", D("200.00"))]
    ytd = dict(data.year_to_date)
    assert ytd["Devengado"] == D("400.00") and ytd["Seguro Social"] == D("39.00")
    assert data.employer == []  # oculto por defecto


def test_ach_summary_and_file(owner_api, tenant, setup, django_capture_on_commit_callbacks):
    run_id = approved_run(
        owner_api,
        tenant,
        setup,
        "2026-11-16",
        "2026-11-22",
        "2026-11-27",
        django_capture_on_commit_callbacks,
    )
    summary = owner_api.get(reverse("payroll-run-ach", args=[run_id])).json()
    assert summary["total"] == "177.29" and summary["blocking"] == []
    assert summary["non_ach"] == [
        {"employee": "E-2 Obra", "method": "Efectivo", "amount": "177.29"}
    ]
    response = owner_api.get(reverse("payroll-run-ach-file", args=[run_id]))
    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows[1][1:8] == [
        "E-1 Obra",
        "8-1-1",
        "Banco General",
        "71",
        "Ahorros",
        "0401234567",
        "177.29",
    ]

    with tenant_context(tenant):
        setup["E-1"].__class__.objects.filter(pk=setup["E-1"].pk).update(
            payment_method="check", bank="", account_number=""
        )
    blocked = owner_api.get(reverse("payroll-run-ach-file", args=[run_id]))
    assert blocked.status_code == 400 and "ACH" in blocked.json()["detail"]


def test_sipe_workbook(owner_api, tenant, roles, setup, django_capture_on_commit_callbacks):
    from openpyxl import load_workbook

    approved_run(
        owner_api,
        tenant,
        setup,
        "2026-11-16",
        "2026-11-22",
        "2026-11-27",
        django_capture_on_commit_callbacks,
    )
    contador = client_for(make_member(tenant, "cont@obra.pa", ["Contador"], roles), tenant)
    response = contador.get(reverse("payroll-sipe"), {"month": "2026-11"})
    assert response.status_code == 200
    wb = load_workbook(io.BytesIO(response.content))
    css = wb["Seguro Social"]
    totals = [c.value for c in css[css.max_row]]
    assert totals[0] == "Totales"
    assert D(str(totals[4])) == D("400.00")  # base CSS de los dos empleados
    assert D(str(totals[5])) == D("39.00")  # 9.75 %
    assert wb["Seguro Educativo"].cell(row=6, column=1).value == "8-1-1"

    jefe = client_for(make_member(tenant, "jefe@obra.pa", ["Jefe de proyecto"], roles), tenant)
    assert jefe.get(reverse("payroll-sipe"), {"month": "2026-11"}).status_code == 403
    assert contador.get(reverse("payroll-sipe"), {"month": "noviembre"}).status_code == 400
