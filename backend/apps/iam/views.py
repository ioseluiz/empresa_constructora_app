from django.contrib.auth import authenticate, password_validation
from django.db import transaction
from django.db.models import Count, Prefetch, ProtectedError, QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.security import SecurityEvent, record_security_event
from apps.accounts.serializers import LoginResponseSerializer
from apps.accounts.views import PublicAuthView, issue_session
from apps.audit import services as audit
from apps.core.tenancy import tenant_context
from apps.tenants.models import Membership
from apps.tenants.permissions import IsTenantMember

from .models import Invitation, Role, RoleAssignment
from .permissions import TenantPermissionMixin, get_request_permissions
from .serializers import (
    PERMISSION_CATALOG,
    InvitationAcceptSerializer,
    InvitationPublicSerializer,
    InvitationSerializer,
    MemberSerializer,
    MyAccessSerializer,
    PermissionSerializer,
    RoleSerializer,
)
from .services import (
    accept_invitation,
    find_invitation,
    invite_member,
    resend_invitation,
    set_member_roles,
)


class PermissionCatalogView(APIView):
    permission_classes = [IsAuthenticated, IsTenantMember]

    @extend_schema(responses=PermissionSerializer(many=True), tags=["iam"])
    def get(self, request: Request) -> Response:
        return Response(PERMISSION_CATALOG)


class MyAccessView(APIView):
    """Permisos efectivos del usuario en la empresa activa (para mostrar/ocultar la UI)."""

    permission_classes = [IsAuthenticated, IsTenantMember]

    @extend_schema(responses=MyAccessSerializer, tags=["iam"])
    def get(self, request: Request) -> Response:
        membership = request.membership  # type: ignore[attr-defined]
        roles = Role.objects.filter(assignments__membership=membership).values_list(
            "name", flat=True
        )
        return Response(
            {
                "is_owner": membership.is_owner,
                "permissions": sorted(get_request_permissions(request)),
                "roles": list(roles),
                "require_mfa": request.tenant.require_mfa,  # type: ignore[attr-defined]
            }
        )


@extend_schema(tags=["iam"])
class RoleViewSet(TenantPermissionMixin, viewsets.ModelViewSet):
    serializer_class = RoleSerializer
    pagination_class = None  # pocas filas por empresa
    action_permissions = {
        "list": "users.view",
        "retrieve": "users.view",
        "create": "roles.manage",
        "update": "roles.manage",
        "partial_update": "roles.manage",
        "destroy": "roles.manage",
    }
    search_fields = ["name"]

    def get_queryset(self) -> QuerySet[Role]:
        return Role.objects.annotate(member_count=Count("assignments")).order_by("name")

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        role = serializer.save(created_by=self.request.user)
        audit.record(audit.Action.CREATE, role, request=self.request, changes=serializer.data)

    def perform_update(self, serializer: serializers.BaseSerializer) -> None:
        before = RoleSerializer(serializer.instance).data
        role = serializer.save(updated_by=self.request.user)
        audit.record(
            audit.Action.UPDATE,
            role,
            request=self.request,
            changes=audit.diff(dict(before), dict(RoleSerializer(role).data)),
        )

    def perform_destroy(self, instance: Role) -> None:
        try:
            with transaction.atomic():
                instance.delete()
        except ProtectedError as exc:
            raise ValidationError(
                "No se puede eliminar un rol asignado a usuarios. Quítalo de los usuarios primero."
            ) from exc
        audit.record(
            audit.Action.DELETE,
            request=self.request,
            object_type="iam.role",
            object_id=str(instance.pk),
            object_repr=instance.name,
        )


@extend_schema(tags=["iam"])
class MemberViewSet(
    TenantPermissionMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = MemberSerializer
    permission_resource = "users"
    http_method_names = ["get", "patch", "head", "options"]
    search_fields = ["user__email", "user__first_name", "user__last_name"]
    filterset_fields = ["is_active"]

    def get_queryset(self) -> QuerySet[Membership]:
        if getattr(self, "swagger_fake_view", False):  # generación del esquema OpenAPI
            return Membership.objects.none()
        # Membership no tiene RLS (se consulta en el login): se filtra explícitamente.
        return (
            Membership.objects.filter(tenant=self.request.tenant)  # type: ignore[attr-defined]
            .select_related("user")
            .prefetch_related(
                Prefetch(
                    "role_assignments",
                    queryset=RoleAssignment.objects.select_related("role").order_by("role__name"),
                )
            )
            .order_by("user__email")
        )

    @staticmethod
    def _snapshot(m: Membership) -> dict:
        return {
            "is_active": m.is_active,
            "roles": sorted(a.role.name for a in m.role_assignments.all()),
        }

    def perform_update(self, serializer: serializers.BaseSerializer) -> None:
        membership: Membership = serializer.instance  # type: ignore[assignment]
        if membership.user_id == self.request.user.pk:
            raise ValidationError("No puedes modificar tu propio acceso.")
        if membership.is_owner:
            raise ValidationError("El administrador principal de la empresa no se puede modificar.")
        before = self._snapshot(membership)
        roles = serializer.validated_data.pop("role_ids", None)
        serializer.save(updated_by=self.request.user)
        if roles is not None:
            set_member_roles(membership, roles)
        membership = self.get_queryset().get(pk=membership.pk)
        serializer.instance = membership
        changes = audit.diff(before, self._snapshot(membership))
        if changes:
            audit.record(
                audit.Action.UPDATE,
                membership,
                request=self.request,
                object_repr=membership.user.email,
                changes=changes,
            )


@extend_schema(tags=["iam"])
class InvitationViewSet(
    TenantPermissionMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = InvitationSerializer
    permission_resource = "users"
    pagination_class = None

    def get_queryset(self) -> QuerySet[Invitation]:
        return (
            Invitation.objects.filter(status=Invitation.Status.PENDING)
            .select_related("created_by")
            .prefetch_related("roles")
        )

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        invitation = invite_member(
            email=serializer.validated_data["email"],
            roles=serializer.validated_data["role_ids"],
            invited_by=self.request.user,  # type: ignore[arg-type]
        )
        serializer.instance = invitation
        audit.record(
            audit.Action.INVITE,
            invitation,
            request=self.request,
            changes={"roles": [r.name for r in invitation.roles.all()]},
        )

    def perform_destroy(self, instance: Invitation) -> None:
        instance.status = Invitation.Status.REVOKED
        instance.save(update_fields=["status", "updated_at"])
        audit.record(audit.Action.REVOKE, instance, request=self.request)

    @extend_schema(request=None, responses=InvitationSerializer)
    @action(detail=True, methods=["post"])
    def resend(self, request: Request, pk: str | None = None) -> Response:
        invitation = resend_invitation(self.get_object(), request.user)  # type: ignore[arg-type]
        return Response(InvitationSerializer(invitation).data)


# ---------------------------------------------------------------------------
# Endpoints públicos: aceptar una invitación recibida por correo
# ---------------------------------------------------------------------------


def _get_usable_invitation(token: str) -> Invitation:
    invitation = find_invitation(token)
    if invitation is None or not invitation.is_usable:
        raise NotFound("La invitación no es válida o ya expiró.")
    return invitation


@extend_schema(tags=["auth"])
class InvitationPublicView(PublicAuthView):
    throttle_scope = "password_reset"

    @extend_schema(responses=InvitationPublicSerializer)
    def get(self, request: Request, token: str) -> Response:
        invitation = _get_usable_invitation(token)
        return Response(
            {
                "email": invitation.email,
                "tenant_name": invitation.tenant.name,
                "user_exists": User.objects.filter(email__iexact=invitation.email).exists(),
            }
        )


@extend_schema(tags=["auth"])
class InvitationAcceptView(PublicAuthView):
    throttle_scope = "login"

    @extend_schema(request=InvitationAcceptSerializer, responses=LoginResponseSerializer)
    def post(self, request: Request, token: str) -> Response:
        invitation = _get_usable_invitation(token)
        data = InvitationAcceptSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        password = data.validated_data["password"]

        user = User.objects.filter(email__iexact=invitation.email).first()
        if user is not None:
            # Cuenta existente: se confirma con su contraseña actual.
            if authenticate(request, username=user.email, password=password) is None:
                raise ValidationError({"password": "La contraseña no es correcta."})
        else:
            candidate = User(
                email=invitation.email,
                first_name=data.validated_data.get("first_name", ""),
                last_name=data.validated_data.get("last_name", ""),
            )
            try:
                password_validation.validate_password(password, candidate)
            except Exception as exc:
                raise ValidationError({"password": list(exc.messages)}) from exc  # type: ignore[attr-defined]
            user = User.objects.create_user(
                invitation.email,
                password,
                first_name=candidate.first_name,
                last_name=candidate.last_name,
            )

        accept_invitation(invitation, user)
        with tenant_context(invitation.tenant):
            audit.record(audit.Action.ACCEPT, invitation, request=request, actor=user)
        record_security_event(SecurityEvent.Type.LOGIN_SUCCESS, request, user=user)
        return issue_session(user, status_code=status.HTTP_201_CREATED)
