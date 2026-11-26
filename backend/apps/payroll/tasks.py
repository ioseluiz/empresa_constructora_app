import logging

from celery import shared_task

from apps.core.tenancy import tenant_context
from apps.tenants.models import Tenant

from .models import PayrollRun
from .payslips import generate_for_run

logger = logging.getLogger(__name__)


@shared_task
def generate_payslips(tenant_id: str, run_id: str) -> int:
    tenant = Tenant.objects.get(pk=tenant_id)
    with tenant_context(tenant):
        return generate_for_run(PayrollRun.objects.get(pk=run_id))
