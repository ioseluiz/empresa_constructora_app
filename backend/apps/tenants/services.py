from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.models import User

from .models import Membership, Tenant


@transaction.atomic
def create_tenant(
    *,
    name: str,
    owner_email: str,
    owner_password: str | None = None,
    slug: str | None = None,
    ruc: str = "",
    dv: str = "",
    legal_name: str = "",
) -> tuple[Tenant, User]:
    """Da de alta una empresa con su usuario administrador (lo crea si no existe)."""
    tenant = Tenant.objects.create(
        name=name,
        legal_name=legal_name or name,
        slug=slug or slugify(name),
        ruc=ruc,
        dv=dv,
    )
    owner = User.objects.filter(email__iexact=owner_email).first()
    if owner is None:
        owner = User.objects.create_user(owner_email, owner_password)
    Membership.objects.create(user=owner, tenant=tenant, is_owner=True)
    from apps.iam.services import create_default_roles
    from apps.organization.services import bootstrap_organization

    create_default_roles(tenant)
    year = timezone.localdate().year
    bootstrap_organization(tenant, years=(year, year + 1))
    from apps.core.tenancy import tenant_context
    from apps.timeclock.services import bootstrap_timeclock

    with tenant_context(tenant):
        bootstrap_timeclock()
    return tenant, owner
