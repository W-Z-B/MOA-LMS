"""How the API documentation describes service-key authentication. Loaded by IntegrationConfig.ready()."""

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class ServiceKeyScheme(OpenApiAuthenticationExtension):
    target_class = "integration.auth.ServiceKeyAuthentication"
    name = "ServiceKey"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
            "description": "Service key issued with create_service_client, sent as `Api-Key <key>`.",
        }
