"""Authentication and scope checks for service clients. Header: `Authorization: Api-Key <key>`."""

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

from integration.models import ServiceClient

KEYWORD = "Api-Key"


class ServiceUser:
    """Stands in for request.user on service calls. It is not a person and holds no roles."""

    is_authenticated = True
    is_active = True
    is_superuser = False
    is_staff = False
    is_service = True
    pk = None
    id = None

    def __init__(self, client: ServiceClient):
        self.client = client
        self.username = f"service:{client.name}"

    def get_username(self) -> str:
        return self.username

    def __str__(self) -> str:
        return self.username


class ServiceKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        parts = get_authorization_header(request).decode("latin-1").split()
        if not parts or parts[0] != KEYWORD:
            return None
        if len(parts) != 2:
            raise AuthenticationFailed("Malformed Api-Key header.")
        client = ServiceClient.authenticate(parts[1])
        if client is None:
            raise AuthenticationFailed("Invalid or inactive service key.")
        ServiceClient.objects.filter(pk=client.pk).update(last_used_at=timezone.now())
        return ServiceUser(client), client

    def authenticate_header(self, request) -> str:
        return KEYWORD


def scope(required: str) -> type[BasePermission]:
    """Permission class factory: the caller must be a service client holding `required`."""

    class HasScope(BasePermission):
        message = f"The service key lacks the '{required}' scope."

        def has_permission(self, request, view) -> bool:
            client = request.auth
            return isinstance(client, ServiceClient) and client.has_scope(required)

    HasScope.__name__ = f"HasScope_{required.replace(':', '_')}"
    return HasScope
