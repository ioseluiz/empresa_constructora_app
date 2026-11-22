import pytest
from django.db import ProgrammingError, connection, transaction
from django.urls import reverse

from apps.audit import services as audit
from apps.audit.models import AuditLog
from apps.core.tenancy import tenant_context
from conftest import client_for, make_member

pytestmark = pytest.mark.django_db


def test_diff_only_changed_fields():
    assert audit.diff({"a": 1, "b": 2}, {"a": 1, "b": 3, "c": None}) == {
        "b": {"antes": 2, "despues": 3}
    }


def test_log_is_append_only(tenant):
    with tenant_context(tenant):
        log = audit.record(audit.Action.EXPORT, object_type="x", object_repr="algo")
    for sql in ("UPDATE audit_auditlog SET object_repr = 'otro'", "DELETE FROM audit_auditlog"):
        with (
            pytest.raises(ProgrammingError, match="no se puede modificar"),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute(sql + " WHERE id = %s", [str(log.pk)])


def test_list_requires_permission_and_filters(owner_api, tenant, roles):
    owner_api.patch(reverse("tenant-current"), {"ruc": "8-1-1"}, format="json")
    response = owner_api.get(reverse("audit-log-list"), {"action": "update"})
    assert response.status_code == 200
    rows = response.json()["results"]
    assert rows[0]["object_type"] == "tenants.tenant"
    assert rows[0]["changes"]["ruc"]["despues"] == "8-1-1"
    assert rows[0]["actor_email"] == "ana@constructora.pa"

    sup = make_member(tenant, "sup@obra.pa", ["Supervisor de obra"], roles)
    assert client_for(sup, tenant).get(reverse("audit-log-list")).status_code == 403


def test_logs_isolated_by_tenant(tenant, other_tenant):
    with tenant_context(tenant):
        audit.record(audit.Action.EXPORT, object_type="x")
    with tenant_context(other_tenant):
        assert AuditLog.objects.count() == 0


@pytest.mark.parametrize(
    ("num_proxies", "xff", "expected"),
    [
        (0, "1.1.1.1", "10.0.0.9"),  # sin proxies se ignora el encabezado
        (1, "6.6.6.6, 2.2.2.2", "2.2.2.2"),  # el valor inventado por el cliente se descarta
        (2, "3.3.3.3, 4.4.4.4", "3.3.3.3"),
    ],
)
def test_client_ip_only_trusts_own_proxies(settings, rf, num_proxies, xff, expected):
    settings.NUM_PROXIES = num_proxies
    request = rf.get("/", HTTP_X_FORWARDED_FOR=xff, REMOTE_ADDR="10.0.0.9")
    assert audit.client_ip(request) == expected
