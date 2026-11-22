from rest_framework.request import Request

from apps.audit.services import client_ip

from .models import SecurityEvent, User

__all__ = ["SecurityEvent", "record_security_event"]


def record_security_event(
    type_: str, request: Request | None, *, user: User | None = None, email: str = ""
) -> SecurityEvent:
    return SecurityEvent.objects.create(
        type=type_,
        user=user,
        email=(email or (user.email if user else "")).lower(),
        ip_address=client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "") if request else "")[:255],
    )
