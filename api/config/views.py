from django.db import connection
from django.http import JsonResponse


def health(request):
    """Liveness and database readiness check used by Compose, Caddy and monitoring."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_ok = True
    except Exception:  # noqa: BLE001 - any failure means not ready
        db_ok = False
    status = 200 if db_ok else 503
    return JsonResponse({"status": "ok" if db_ok else "degraded", "database": db_ok}, status=status)
