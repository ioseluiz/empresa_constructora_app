from contextlib import suppress

from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from . import mfa
from .cookies import REFRESH_COOKIE, clear_refresh_cookie, set_refresh_cookie
from .emails import send_password_reset_email
from .models import SecurityEvent, User
from .security import record_security_event
from .serializers import (
    AccessTokenSerializer,
    LoginResponseSerializer,
    LoginResultSerializer,
    LoginSerializer,
    MFACodeSerializer,
    MFADisableSerializer,
    MFALoginSerializer,
    MFASetupSerializer,
    MFAStatusSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RecoveryCodesSerializer,
    UserSerializer,
)

INVALID_CREDENTIALS = "Correo o contraseña incorrectos."
Event = SecurityEvent.Type


def issue_session(user: User, status_code: int = status.HTTP_200_OK) -> Response:
    """Emite access token (en el cuerpo) y refresh token (cookie httpOnly)."""
    update_last_login(User, user)
    refresh = RefreshToken.for_user(user)
    response = Response(
        {"access": str(refresh.access_token), "user": UserSerializer(user).data},
        status=status_code,
    )
    set_refresh_cookie(response, str(refresh))
    return response


def auth_failed(detail: str) -> Response:
    """401 sin lanzar excepción: el handler de DRF deshace la transacción ante excepciones
    (ATOMIC_REQUESTS) y se perdería el registro del intento fallido."""
    return Response({"detail": detail}, status=status.HTTP_401_UNAUTHORIZED)


def _current_user(request: Request) -> User:
    return request.user  # type: ignore[return-value]


class PublicAuthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get_authenticate_header(self, request: Request) -> str:
        # Sin clases de autenticación DRF convertiría los 401 en 403.
        return 'Bearer realm="api"'


class LoginView(PublicAuthView):
    throttle_scope = "login"

    @extend_schema(request=LoginSerializer, responses=LoginResultSerializer, tags=["auth"])
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        user = authenticate(request, username=email, password=serializer.validated_data["password"])
        if user is None:
            record_security_event(Event.LOGIN_FAILED, request, email=email)
            return auth_failed(INVALID_CREDENTIALS)
        if user.mfa_enabled:
            return Response({"mfa_required": True, "mfa_token": mfa.make_login_token(user)})
        record_security_event(Event.LOGIN_SUCCESS, request, user=user)
        return issue_session(user)


class MFALoginView(PublicAuthView):
    throttle_scope = "mfa"

    @extend_schema(request=MFALoginSerializer, responses=LoginResponseSerializer, tags=["auth"])
    def post(self, request: Request) -> Response:
        serializer = MFALoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = mfa.read_login_token(serializer.validated_data["mfa_token"])
        if user is None:
            raise AuthenticationFailed("La verificación expiró. Inicia sesión de nuevo.")
        ok, used_recovery = mfa.verify_second_factor(user, serializer.validated_data["code"])
        if not ok:
            record_security_event(Event.MFA_FAILED, request, user=user)
            return auth_failed("El código no es válido.")
        if used_recovery:
            record_security_event(Event.MFA_RECOVERY_USED, request, user=user)
        record_security_event(Event.LOGIN_SUCCESS, request, user=user)
        return issue_session(user)


class RefreshView(PublicAuthView):
    """Emite un access token nuevo a partir de la cookie y rota el refresh token."""

    throttle_scope = "refresh"

    @extend_schema(request=None, responses=AccessTokenSerializer, tags=["auth"])
    def post(self, request: Request) -> Response:
        raw = request.COOKIES.get(REFRESH_COOKIE)
        if not raw:
            raise AuthenticationFailed("Sesión no iniciada.")
        try:
            old = RefreshToken(raw)  # type: ignore[arg-type]
            user = User.objects.get(pk=old["user_id"], is_active=True)
            old.blacklist()
        except (TokenError, User.DoesNotExist):
            response = Response(
                {"detail": "La sesión expiró. Inicia sesión de nuevo."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            clear_refresh_cookie(response)
            return response
        new = RefreshToken.for_user(user)
        response = Response({"access": str(new.access_token)})
        set_refresh_cookie(response, str(new))
        return response


class LogoutView(PublicAuthView):
    @extend_schema(request=None, responses={204: None}, tags=["auth"])
    def post(self, request: Request) -> Response:
        raw = request.COOKIES.get(REFRESH_COOKIE)
        if raw:
            with suppress(TokenError):
                token = RefreshToken(raw)  # type: ignore[arg-type]
                user = User.objects.filter(pk=token["user_id"]).first()
                token.blacklist()
                record_security_event(Event.LOGOUT, request, user=user)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_refresh_cookie(response)
        return response


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=UserSerializer, tags=["auth"])
    def get(self, request: Request) -> Response:
        return Response(UserSerializer(request.user).data)

    @extend_schema(request=UserSerializer, responses=UserSerializer, tags=["auth"])
    def patch(self, request: Request) -> Response:
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PasswordResetRequestView(PublicAuthView):
    throttle_scope = "password_reset"

    @extend_schema(
        request=PasswordResetRequestSerializer,
        responses={204: OpenApiResponse(description="Siempre 204, exista o no el correo.")},
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        record_security_event(Event.PASSWORD_RESET_REQUESTED, request, user=user, email=email)
        if user is not None:
            send_password_reset_email(user)
        # Misma respuesta exista o no la cuenta: no revela qué correos están registrados.
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetConfirmView(PublicAuthView):
    throttle_scope = "password_reset"

    @extend_schema(request=PasswordResetConfirmSerializer, responses={204: None}, tags=["auth"])
    def post(self, request: Request) -> Response:
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        record_security_event(Event.PASSWORD_RESET_DONE, request, user=user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=PasswordChangeSerializer, responses={204: None}, tags=["auth"])
    def post(self, request: Request) -> Response:
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = _current_user(request)
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        record_security_event(Event.PASSWORD_CHANGED, request, user=user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Configuración de MFA de la propia cuenta
# ---------------------------------------------------------------------------


class MFAStatusView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=MFAStatusSerializer, tags=["mfa"])
    def get(self, request: Request) -> Response:
        user = _current_user(request)
        return Response(
            {
                "enabled": user.mfa_enabled,
                "recovery_codes_remaining": mfa.remaining_recovery_codes(user),
            }
        )


class MFASetupView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses=MFASetupSerializer, tags=["mfa"])
    def post(self, request: Request) -> Response:
        user = _current_user(request)
        if user.mfa_enabled:
            raise ValidationError("La verificación en dos pasos ya está activa.")
        return Response(mfa.start_setup(user))


class MFAEnableView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "mfa"

    @extend_schema(request=MFACodeSerializer, responses=RecoveryCodesSerializer, tags=["mfa"])
    def post(self, request: Request) -> Response:
        user = _current_user(request)
        serializer = MFACodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if user.mfa_enabled:
            raise ValidationError("La verificación en dos pasos ya está activa.")
        if not mfa.verify_totp(user, serializer.validated_data["code"].strip()):
            raise ValidationError({"code": "El código no es válido. Revisa la hora del teléfono."})
        codes = mfa.enable(user)
        record_security_event(Event.MFA_ENABLED, request, user=user)
        return Response({"recovery_codes": codes})


class MFADisableView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "mfa"

    @extend_schema(request=MFADisableSerializer, responses={204: None}, tags=["mfa"])
    def post(self, request: Request) -> Response:
        user = _current_user(request)
        serializer = MFADisableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not user.check_password(serializer.validated_data["password"]):
            raise ValidationError({"password": "La contraseña no es correcta."})
        ok, _ = mfa.verify_second_factor(user, serializer.validated_data["code"])
        if not ok:
            raise ValidationError({"code": "El código no es válido."})
        mfa.disable(user)
        record_security_event(Event.MFA_DISABLED, request, user=user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MFARecoveryCodesView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "mfa"

    @extend_schema(request=MFACodeSerializer, responses=RecoveryCodesSerializer, tags=["mfa"])
    def post(self, request: Request) -> Response:
        user = _current_user(request)
        serializer = MFACodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not user.mfa_enabled or not mfa.verify_totp(user, serializer.validated_data["code"]):
            raise ValidationError({"code": "El código no es válido."})
        return Response({"recovery_codes": mfa.generate_recovery_codes(user)})
