from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.core.tenancy import tenant_context
from apps.organization import panama
from apps.organization.models import CBACategory, CBAWageRate, CostCenter, Holiday, Position
from apps.tenants.services import create_tenant
from conftest import PASSWORD, client_for, make_member

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("year", "carnival", "good_friday"),
    [(2025, date(2025, 3, 4), date(2025, 4, 18)), (2026, date(2026, 2, 17), date(2026, 4, 3))],
)
def test_movable_holidays(year, carnival, good_friday):
    days = {name: d for d, name, _ in panama.national_holidays(year)}
    assert days["Martes de Carnaval"] == carnival
    assert days["Viernes Santo"] == good_friday
    assert len(days) == 12


def test_new_tenant_is_bootstrapped(db):
    tenant, _ = create_tenant(name="Obra Nueva", owner_email="d@o.pa", owner_password=PASSWORD)
    with tenant_context(tenant):
        assert CostCenter.objects.get(code="OC").kind == "office"
        assert CBACategory.objects.count() == len(panama.CBA_CATEGORIES)
        assert Position.objects.get(code="ALB").cba_category.code == "ALB"
        assert Holiday.objects.filter(date__year=date.today().year).count() == 12


@pytest.fixture
def org_api(owner_api, tenant):
    from apps.organization.services import bootstrap_organization

    bootstrap_organization(tenant, years=(2026,))
    return owner_api


class TestCatalogPermissions:
    def test_any_member_can_read_but_not_write(self, org_api, tenant, roles):
        sup = make_member(tenant, "sup@obra.pa", ["Supervisor de obra"], roles)
        api = client_for(sup, tenant)
        assert api.get(reverse("position-list")).status_code == 200
        response = api.post(reverse("position-list"), {"code": "X", "name": "X"}, format="json")
        assert response.status_code == 403

    def test_hr_can_manage(self, org_api, tenant, roles):
        hr = make_member(tenant, "rrhh@obra.pa", ["Recursos humanos"], roles)
        response = client_for(hr, tenant).post(
            reverse("position-list"), {"code": "top", "name": "Topógrafo"}, format="json"
        )
        assert response.status_code == 201
        assert response.json()["code"] == "TOP"


class TestCostCenters:
    def test_tree_and_cycle_prevention(self, org_api):
        parent = org_api.post(
            reverse("cost-center-list"), {"code": "ADM", "name": "Administración"}, format="json"
        ).json()
        child = org_api.post(
            reverse("cost-center-list"),
            {"code": "ADM-TI", "name": "TI", "parent": parent["id"]},
            format="json",
        ).json()
        response = org_api.patch(
            reverse("cost-center-detail", args=[parent["id"]]),
            {"parent": child["id"]},
            format="json",
        )
        assert response.status_code == 400

    def test_duplicate_code(self, org_api):
        response = org_api.post(
            reverse("cost-center-list"), {"code": "oc", "name": "Otra"}, format="json"
        )
        assert response.status_code == 400

    def test_cannot_create_project_kind_or_delete_office(self, org_api, tenant):
        response = org_api.post(
            reverse("cost-center-list"),
            {"code": "P1", "name": "x", "kind": "project"},
            format="json",
        )
        assert response.status_code == 400
        with tenant_context(tenant):
            office = CostCenter.objects.get(code="OC")
        assert org_api.delete(reverse("cost-center-detail", args=[office.pk])).status_code == 400


class TestCBA:
    def test_rates_by_validity(self, org_api, tenant):
        with tenant_context(tenant):
            cat = CBACategory.objects.get(code="ALB")
        for valid_from, rate in [("2025-01-01", "4.50"), ("2026-01-01", "4.80")]:
            response = org_api.post(
                reverse("cba-rate-list"),
                {"category": str(cat.pk), "hourly_rate": rate, "valid_from": valid_from},
                format="json",
            )
            assert response.status_code == 201, response.json()
        with tenant_context(tenant):
            assert cat.rate_on(date(2025, 6, 1)).hourly_rate == Decimal("4.5")
            assert cat.rate_on(date(2026, 6, 1)).hourly_rate == Decimal("4.8")
            assert cat.rate_on(date(2024, 6, 1)) is None
        dup = org_api.post(
            reverse("cba-rate-list"),
            {"category": str(cat.pk), "hourly_rate": "5", "valid_from": "2026-01-01"},
            format="json",
        )
        assert dup.status_code == 400

    def test_category_in_use_cannot_be_deleted(self, org_api, tenant):
        with tenant_context(tenant):
            cat = CBACategory.objects.get(code="ALB")
        assert org_api.delete(reverse("cba-category-detail", args=[cat.pk])).status_code == 400

    def test_rates_isolated(self, org_api, tenant, other_tenant):
        with tenant_context(tenant):
            cat = CBACategory.objects.get(code="ALB")
            CBAWageRate.objects.create(category=cat, hourly_rate="4", valid_from=date(2026, 1, 1))
        with tenant_context(other_tenant):
            assert CBAWageRate.objects.count() == 0


class TestHolidays:
    def test_generate_and_filter_by_year(self, org_api):
        response = org_api.post(reverse("holiday-generate"), {"year": 2027}, format="json")
        assert response.status_code == 201
        assert len(response.json()) == 12
        again = org_api.post(reverse("holiday-generate"), {"year": 2027}, format="json")
        assert again.json() == []
        rows = org_api.get(reverse("holiday-list"), {"year": 2027}).json()
        assert len(rows) == 12

    def test_add_decreed_day(self, org_api):
        response = org_api.post(
            reverse("holiday-list"),
            {"date": "2026-11-04", "name": "Día de la Bandera (decretado)", "kind": "decreed"},
            format="json",
        )
        assert response.status_code == 201
        dup = org_api.post(
            reverse("holiday-list"), {"date": "2026-11-04", "name": "x"}, format="json"
        )
        assert dup.status_code == 400
