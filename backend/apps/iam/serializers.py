from typing import cast

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.relations import ManyRelatedField

from apps.projects.models import Project
from apps.tenants.models import Membership

from .catalog import PERMISSIONS
from .models import Invitation, Role, validate_permission_codes


class PermissionSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]
    module = serializers.CharField()


class MyAccessSerializer(serializers.Serializer):
    is_owner = serializers.BooleanField()
    permissions = serializers.ListField(child=serializers.CharField())
    roles = serializers.ListField(child=serializers.CharField())
    require_mfa = serializers.BooleanField()


class RoleSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Role
        fields = ["id", "name", "description", "permissions", "is_system", "member_count"]
        read_only_fields = ["id", "is_system", "member_count"]

    def validate_permissions(self, value: list[str]) -> list[str]:
        try:
            validate_permission_codes(value)
        except Exception as exc:
            raise serializers.ValidationError(str(exc.args[0])) from exc
        return sorted(set(value))

    def validate_name(self, value: str) -> str:
        qs = Role.objects.filter(name__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe un rol con ese nombre.")
        return value


class RoleRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "name"]


class MemberUserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    full_name = serializers.CharField()
    last_login = serializers.DateTimeField(allow_null=True)
    mfa_enabled = serializers.BooleanField()


class ProjectRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()


class AssignmentSerializer(serializers.Serializer):
    role = RoleRefSerializer()
    projects = ProjectRefSerializer(many=True, help_text="Vacío: todos los proyectos.")


class AssignmentWriteSerializer(serializers.Serializer):
    role_id = serializers.PrimaryKeyRelatedField(queryset=Role.objects.none())
    project_ids = serializers.PrimaryKeyRelatedField(
        queryset=Project.objects.none(), many=True, required=False
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["role_id"].queryset = Role.objects.all()  # type: ignore[attr-defined]
        field = cast(ManyRelatedField, self.fields["project_ids"])
        field.child_relation.queryset = Project.objects.all()  # type: ignore[arg-type]


class MemberSerializer(serializers.ModelSerializer):
    user = MemberUserSerializer(read_only=True)
    assignments = serializers.SerializerMethodField()
    set_assignments = AssignmentWriteSerializer(
        many=True,
        write_only=True,
        required=False,
        help_text="Reemplaza todos los roles del miembro.",
    )

    class Meta:
        model = Membership
        fields = [
            "id",
            "user",
            "is_owner",
            "is_active",
            "assignments",
            "set_assignments",
            "created_at",
        ]
        read_only_fields = ["id", "is_owner", "created_at"]

    @extend_schema_field(AssignmentSerializer(many=True))
    def get_assignments(self, membership: Membership) -> list[dict]:
        return [
            {
                "role": {"id": a.role.pk, "name": a.role.name},
                "projects": [
                    {"id": p.pk, "code": p.code, "name": p.name}
                    for p in sorted(a.projects.all(), key=lambda p: p.code)
                ],
            }
            for a in membership.role_assignments.all()
        ]

    def validate_set_assignments(self, value: list[dict]) -> list[dict]:
        role_ids = [item["role_id"].pk for item in value]
        if len(role_ids) != len(set(role_ids)):
            raise serializers.ValidationError("Un rol no puede repetirse.")
        return value


class InvitationSerializer(serializers.ModelSerializer):
    roles = RoleRefSerializer(many=True, read_only=True)
    role_ids = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.none(), many=True, write_only=True
    )
    invited_by = serializers.EmailField(source="created_by.email", read_only=True, default="")
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = Invitation
        fields = [
            "id",
            "email",
            "roles",
            "role_ids",
            "status",
            "expires_at",
            "is_expired",
            "invited_by",
            "created_at",
        ]
        read_only_fields = ["id", "status", "expires_at", "created_at"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        field = cast(ManyRelatedField, self.fields["role_ids"])
        field.child_relation.queryset = Role.objects.all()  # type: ignore[arg-type]

    def validate_role_ids(self, value: list[Role]) -> list[Role]:
        if not value:
            raise serializers.ValidationError("Asigna al menos un rol.")
        return value


class InvitationPublicSerializer(serializers.Serializer):
    email = serializers.EmailField()
    tenant_name = serializers.CharField()
    user_exists = serializers.BooleanField()


class InvitationAcceptSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False)


PERMISSION_CATALOG = [{"code": p.code, "label": p.label, "module": p.module} for p in PERMISSIONS]
