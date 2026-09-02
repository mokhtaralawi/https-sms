import logging
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework import status
from rest_framework.response import Response


def custom_exception_handler(exc, context):
    """
    Custom DRF exception handler returning a consistent error envelope.
    """
    if hasattr(exc, "status_code"):
        response = drf_exception_handler(exc, context)
        if response is not None:
            response.data = {
                "success": False,
                "error": _flatten_errors(response.data),
            }
            return response

    # Fallback
    logging.getLogger("httpsms").exception("Unhandled API exception", exc_info=exc)
    return Response(
        {
            "success": False,
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred.",
            }
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _flatten_errors(data):
    if isinstance(data, dict):
        if "detail" in data and len(data) == 1:
            return {"code": "error", "message": str(data["detail"])}
        return {k: _flatten_errors(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_flatten_errors(item) for item in data]
    return data
