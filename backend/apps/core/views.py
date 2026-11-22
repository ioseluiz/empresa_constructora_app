from django.db import connection
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Chequeo de salud para el balanceador de carga y el pipeline de despliegue."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(
        responses=inline_serializer(
            "Health",
            fields={"status": serializers.CharField(), "database": serializers.CharField()},
        )
    )
    def get(self, request: Request) -> Response:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            db_status = "ok"
        except Exception:
            db_status = "error"
        status_code = 200 if db_status == "ok" else 503
        return Response(
            {"status": "ok" if status_code == 200 else "degraded", "database": db_status},
            status=status_code,
        )
