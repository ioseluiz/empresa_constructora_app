import pytest
from django.urls import reverse

from apps.tenants.models import Membership
from apps.tenants.services import create_tenant

pytestmark = pytest.mark.django_db
URL = "tenant-current"


def test_requires_tenant_header(auth_api, membership):
    assert auth_api.get(reverse(URL)).status_code == 403


def test_member_gets_tenant(auth_api, membership, tenant):
    response = auth_api.get(reverse(URL), HTTP_X_TENANT_ID=str(tenant.pk))
    assert response.status_code == 200
    assert response.json()["name"] == "Constructora Istmo"


@pytest.mark.parametrize("header", ["no-es-uuid", "00000000-0000-0000-0000-000000000000"])
def test_bad_header(auth_api, membership, header):
    assert auth_api.get(reverse(URL), HTTP_X_TENANT_ID=header).status_code == 403


def test_non_member_cannot_access_other_tenant(auth_api, membership, other_tenant):
    response = auth_api.get(reverse(URL), HTTP_X_TENANT_ID=str(other_tenant.pk))
    assert response.status_code == 403


def test_inactive_tenant_blocked(auth_api, membership, tenant):
    tenant.is_active = False
    tenant.save()
    assert auth_api.get(reverse(URL), HTTP_X_TENANT_ID=str(tenant.pk)).status_code == 403


def test_owner_can_update_profile(auth_api, membership, tenant):
    response = auth_api.patch(
        reverse(URL),
        {"ruc": "8-888-888", "dv": "45"},
        format="json",
        HTTP_X_TENANT_ID=str(tenant.pk),
    )
    assert response.status_code == 200
    tenant.refresh_from_db()
    assert (tenant.ruc, tenant.dv) == ("8-888-888", "45")


def test_non_owner_cannot_update(auth_api, membership, tenant):
    Membership.objects.filter(pk=membership.pk).update(is_owner=False)
    response = auth_api.patch(
        reverse(URL), {"name": "Hackeada"}, format="json", HTTP_X_TENANT_ID=str(tenant.pk)
    )
    assert response.status_code == 403


def test_create_tenant_service_reuses_existing_user(user):
    tenant, owner = create_tenant(name="Nueva Obra S.A.", owner_email="ANA@constructora.pa")
    assert owner == user
    assert tenant.slug == "nueva-obra-sa"
    assert Membership.objects.get(user=user, tenant=tenant).is_owner
