import logging
import time

from django.http import HttpResponse
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger("httpsms.audit")


class AuditMiddleware(MiddlewareMixin):
    """Middleware that records basic request audit information."""

    def process_request(self, request):
        request._start_time = time.time()
        return None

    def process_response(self, request, response):
        if not hasattr(request, "_start_time"):
            return response

        try:
            duration = (time.time() - request._start_time) * 1000
            user = request.user if hasattr(request, "user") else None

            from audit.models import AuditLog

            log_data = {
                "action": self._infer_action(request),
                "resource_type": self._resource_type(request),
                "resource_id": None,
                "ip_address": self._get_client_ip(request),
                "user_agent": (request.META.get("HTTP_USER_AGENT") or "")[:500],
                "status_code": response.status_code,
                "metadata": {
                    "method": request.method,
                    "path": request.path,
                    "duration_ms": round(duration, 2),
                },
            }
            if user is not None and getattr(user, "is_authenticated", False):
                log_data["user"] = user
                if getattr(user, "customer_id", None):
                    log_data["customer"] = user.customer

            # Only audit API and device endpoints to avoid table bloat
            if request.path.startswith("/api/") or request.path.startswith("/ws/") or request.method != "GET":
                AuditLog.objects.create(**log_data)
        except Exception as exc:  # pragma: no cover
            logger.debug("Audit log error: %s", exc)

        return response

    def _infer_action(self, request):
        method = request.method.upper()
        path = request.path.strip("/")
        parts = [p for p in path.split("/") if p]
        cloud = ".".join(parts[:3])
        if method == "GET":
            return "read" if not cloud else f"{cloud}.read"
        return f"{cloud}.{method.lower()}"

    def _resource_type(self, request):
        parts = [p for p in request.path.strip("/").split("/") if p]
        if parts and parts[0] == "api" and len(parts) >= 3:
            return parts[2]
        return "unknown"

    def _get_client_ip(self, request):
        x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded:
            return x_forwarded.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "")


class AsyncAuditLogger:
    """Helper to audit log from async contexts (e.g., WebSocket consumer)."""

    @staticmethod
    async def log(action: str, resource_type: str = "", resource_id=None, user=None,
                  customer=None, metadata=None):
        from audit.models import AuditLog

        try:
            from asgiref.sync import sync_to_async

            await sync_to_async(AuditLog.objects.create)(
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                user=user,
                customer=customer,
                metadata=metadata or {},
            )
        except Exception as exc:  # pragma: no cover
            logger.debug("Async audit log error: %s", exc)