from django.contrib.auth import password_validation
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.tenants.models import Membership

from .models import User


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class MembershipSerializer(serializers.ModelSerializer):
    tenant_id = serializers.UUIDField(source="tenant.id", read_only=True)
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    tenant_slug = serializers.CharField(source="tenant.slug", read_only=True)
    require_mfa = serializers.BooleanField(source="tenant.require_mfa", read_only=True)

    class Meta:
        model = Membership
        fields = ["tenant_id", "tenant_name", "tenant_slug", "is_owner", "require_mfa"]


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    memberships = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "mfa_enabled",
            "memberships",
        ]
        read_only_fields = ["id", "email", "mfa_enabled"]

    @extend_schema_field(MembershipSerializer(many=True))
    def get_memberships(self, user: User) -> list[dict]:
        qs = (
            Membership.objects.filter(user=user, is_active=True, tenant__is_active=True)
            .select_related("tenant")
            .order_by("tenant__name")
        )
        return MembershipSerializer(qs, many=True).data  # type: ignore[return-value]


class AccessTokenSerializer(serializers.Serializer):
    access = serializers.CharField()


class LoginResponseSerializer(AccessTokenSerializer):
    user = UserSerializer()


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    default_error_messages = {"invalid_link": "El enlace no es válido o ya expiró."}

    def validate(self, attrs: dict) -> dict:
        try:
            pk = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=pk, is_active=True)
        except (ValueError, TypeError, OverflowError, User.DoesNotExist) as exc:
            self.fail("invalid_link")
            raise AssertionError from exc  # inalcanzable: fail() lanza ValidationError
        if not default_token_generator.check_token(user, attrs["token"]):
            self.fail("invalid_link")
        password_validation.validate_password(attrs["new_password"], user)
        attrs["user"] = user
        return attrs


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_current_password(self, value: str) -> str:
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("La contraseña actual no es correcta.")
        return value

    def validate_new_password(self, value: str) -> str:
        password_validation.validate_password(value, self.context["request"].user)
        return value


class LoginResultSerializer(serializers.Serializer):
    """Respuesta del login: sesión completa, o `mfa_required` con un token intermedio."""

    access = serializers.CharField(required=False)
    user = UserSerializer(required=False)
    mfa_required = serializers.BooleanField(required=False)
    mfa_token = serializers.CharField(required=False)


class MFALoginSerializer(serializers.Serializer):
    mfa_token = serializers.CharField()
    code = serializers.CharField(max_length=20)


class MFAStatusSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    recovery_codes_remaining = serializers.IntegerField()


class MFASetupSerializer(serializers.Serializer):
    secret = serializers.CharField()
    otpauth_uri = serializers.CharField()
    qr_svg = serializers.CharField()


class MFACodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=20)


class MFADisableSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    code = serializers.CharField(max_length=20)


class RecoveryCodesSerializer(serializers.Serializer):
    recovery_codes = serializers.ListField(child=serializers.CharField())
