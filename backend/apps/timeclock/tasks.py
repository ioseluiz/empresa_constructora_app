import logging

from celery import shared_task

from apps.core.tenancy import tenant_context
from apps.tenants.models import Tenant

from .models import ImportBatch
from .services import process_batch

logger = logging.getLogger(__name__)


@shared_task
def process_import_batch(tenant_id: str, batch_id: str) -> str:
    tenant = Tenant.objects.get(pk=tenant_id)
    try:
        with tenant_context(tenant):
            batch = ImportBatch.objects.get(pk=batch_id)
            if batch.status != ImportBatch.Status.PENDING:
                return batch.status
            return process_batch(batch).status
    except Exception:
        # La transacción del procesamiento se revirtió: se deja constancia en el lote.
        logger.exception("Error procesando el lote de marcaciones %s", batch_id)
        with tenant_context(tenant):
            ImportBatch.objects.filter(pk=batch_id).update(
                status=ImportBatch.Status.FAILED,
                error=(
                    "Error inesperado al procesar el archivo. "
                    "Revisa el formato e inténtalo de nuevo."
                ),
            )
        return ImportBatch.Status.FAILED
