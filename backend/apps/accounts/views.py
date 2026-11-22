from contextlib import suppress

from django.contrib.auth import authenticate, update_session_auth_hash
from django.contrib.auth.models import update_last_login
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .cookies import REFRESH_COOKIE, clear_refresh_cookie, set_refresh_cookie
from .emails import send_password_reset_email
from .models import User
from .serializers import (
    AccessTokenSerializer,
    LoginResponseSerializer,
    LoginSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    UserSerializer,
)

INVALID_CREDENTIALS = "Correo o contraseña incorrectos."


class PublicAuthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get_authenticate_header(self, request: Request) -> str:
        # Sin clases de autenticación DRF convertiría los 401 en 403.
        return 'Bearer realm="api"'


class LoginView(PublicAuthView):
    throttle_scope = "login"

    @extend_schema(request=LoginSerializer, responses=LoginResponseSerializer, tags=["auth"])
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            raise AuthenticationFailed(INVALID_CREDENTIALS)
        update_last_login(User, user)
        refresh = RefreshToken.for_user(user)
        response = Response(
            {"access": str(refresh.access_token), "user": UserSerializer(user).data}
        )
        set_refresh_cookie(response, str(refresh))
        return response


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
                RefreshToken(raw).blacklist()  # type: ignore[arg-type]
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
        user = User.objects.filter(
            email__iexact=serializer.validated_data["email"], is_active=True
        ).first()
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
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=PasswordChangeSerializer, responses={204: None}, tags=["auth"])
    def post(self, request: Request) -> Response:
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user: User = request.user  # type: ignore[assignment]
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        update_session_auth_hash(request, user)
        return Response(status=status.HTTP_204_NO_CONTENT)
