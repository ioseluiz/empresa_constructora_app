from typing import Final, Literal
from uuid import UUID

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User
from apps.core.tenancy import bypass_tenant_scope, require_current_tenant, tenant_context
from apps.tenants.models import Membership, Tenant

from .catalog import ALL, DEFAULT_ROLES
from .models import Invitation, Role, RoleAssignment, hash_token


def create_default_roles(tenant: Tenant) -> list[Role]:
    with tenant_context(tenant):
        return [
            Role.objects.get_or_create(
                name=name,
                defaults={
                    "description": spec["description"],
                    "permissions": spec["permissions"],
                    "is_system": True,
                },
            )[0]
            for name, spec in DEFAULT_ROLES.items()
        ]


ALL_PROJECTS: Final = "all"
Scope = Literal["all"] | frozenset[UUID]


def _assignments(membership: Membership) -> list[RoleAssignment]:
    return list(
        RoleAssignment.objects.filter(membership=membership)
        .select_related("role")
        .prefetch_related("projects")
    )


def effective_permissions(membership: Membership) -> set[str]:
    """Permisos del miembro en la empresa activa, en cualquier alcance (para mostrar la UI y
    el control grueso). El propietario tiene todos. El alcance por proyecto lo resuelve
    `permission_scope`."""
    if membership.is_owner:
        return set(ALL)
    perms: set[str] = set()
    for assignment in _assignments(membership):
        perms.update(assignment.role.permissions)
    return perms


def permission_scope(membership: Membership, permission: str) -> Scope:
    """Proyectos donde el miembro tiene el permiso: "all" o un conjunto (posiblemente vacío)."""
    if membership.is_owner:
        return ALL_PROJECTS
    project_ids: set[UUID] = set()
    for assignment in _assignments(membership):
        if permission not in assignment.role.permissions:
            continue
        ids = {p.pk for p in assignment.projects.all()}
        if not ids:
            return ALL_PROJECTS
        project_ids |= ids
    return frozenset(project_ids)


def set_member_roles(membership: Membership, roles: list[Role]) -> None:
    """Asigna roles con alcance de toda la empresa (usado por invitaciones)."""
    set_member_assignments(membership, [(role, []) for role in roles])


def set_member_assignments(membership: Membership, assignments: list[tuple[Role, list]]) -> None:
    """Reemplaza las asignaciones del miembro por [(rol, [proyectos])]."""
    wanted = {role.pk: (role, projects) for role, projects in assignments}
    RoleAssignment.objects.filter(membership=membership).exclude(role_id__in=wanted).delete()
    for role, projects in wanted.values():
        assignment, _ = RoleAssignment.objects.get_or_create(membership=membership, role=role)
        assignment.projects.set(projects)


def _send_invitation_email(invitation: Invitation, token: str, invited_by: User) -> None:
    link = f"{settings.FRONTEND_URL}/aceptar-invitacion?token={token}"
    send_mail(
        subject=f"Invitación a {invitation.tenant.name}",
        message=(
            f"{invited_by.full_name} te invitó a unirte a {invitation.tenant.name} "
            "en la plataforma de gestión.\n\n"
            f"Acepta la invitación aquí (válida por {Invitation.INVITATION_TTL.days} días):\n"
            f"{link}\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[invitation.email],
    )


@transaction.atomic
def invite_member(*, email: str, roles: list[Role], invited_by: User) -> Invitation:
    email = email.lower()
    if Membership.objects.filter(
        tenant=require_current_tenant(), user__email__iexact=email, is_active=True
    ).exists():
        raise ValidationError({"email": "Este usuario ya es miembro de la empresa."})
    if Invitation.objects.filter(email=email, status=Invitation.Status.PENDING).exists():
        raise ValidationError({"email": "Ya hay una invitación pendiente para este correo."})
    invitation = Invitation(email=email, created_by=invited_by)
    token = invitation.issue_token()
    invitation.save()
    invitation.roles.set(roles)
    _send_invitation_email(invitation, token, invited_by)
    return invitation


@transaction.atomic
def resend_invitation(invitation: Invitation, invited_by: User) -> Invitation:
    if invitation.status != Invitation.Status.PENDING:
        raise ValidationError("Solo se pueden reenviar invitaciones pendientes.")
    token = invitation.issue_token()
    invitation.save(update_fields=["token_hash", "expires_at", "updated_at"])
    _send_invitation_email(invitation, token, invited_by)
    return invitation


def find_invitation(token: str) -> Invitation | None:
    """Búsqueda pública por token (aún no se sabe la empresa): requiere saltar el filtro."""
    with bypass_tenant_scope():
        return (
            Invitation.objects.select_related("tenant").filter(token_hash=hash_token(token)).first()
        )


@transaction.atomic
def accept_invitation(invitation: Invitation, user: User) -> Membership:
    if not invitation.is_usable:
        raise ValidationError("La invitación no es válida o ya expiró.")
    if user.email.lower() != invitation.email:
        raise ValidationError("La invitación pertenece a otro correo.")
    with tenant_context(invitation.tenant):
        membership, created = Membership.objects.get_or_create(
            user=user, tenant=invitation.tenant, defaults={"created_by": invitation.created_by}
        )
        if not created and not membership.is_active:
            membership.is_active = True
            membership.save(update_fields=["is_active", "updated_at"])
        set_member_roles(membership, list(invitation.roles.all()))
        invitation.status = Invitation.Status.ACCEPTED
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=["status", "accepted_at", "updated_at"])
    return membership
