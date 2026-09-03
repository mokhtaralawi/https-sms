import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from api_keys.models import APIKey
from devices.models import SimCard
from messaging.services.sender import MessageValidationError, process_single_message

logger = logging.getLogger("httpsms.compat")


class XApiKeyPermission(BasePermission):
    """Authenticate via the `x-api-key` header (httpSMS-style) and attach the
    resolved principal to `request.user`."""

    def has_permission(self, request, view):
        raw_key = (request.headers.get("x-api-key") or "").strip()
        if not raw_key:
            return False

        api_key = APIKey.find_by_raw_key(raw_key)
        if api_key is None or not api_key.is_active:
            return False

        customer = api_key.customer
        if customer is None or customer.status != customer.ACTIVE:
            return False

        api_key.touch_used()

        from api_keys.authentication import APIKeyPrincipal
        request.user = APIKeyPrincipal(api_key)
        return True


def _customer_from_request(request):
    from api_keys.authentication import APIKeyPrincipal
    user = request.user
    if isinstance(user, APIKeyPrincipal):
        return user.customer, user.api_key
    return None, None


def _matches_phone(phone_number, candidate):
    """Compare an E.164-ish number to a stored SIM phone number, tolerating
    formatting differences (spaces, dashes, missing leading +)."""
    if not candidate:
        return False
    phone = phone_number.strip()

    def normalize(v):
        return "".join(ch for ch in v if ch.isdigit())

    return normalize(phone).lstrip("0") == normalize(candidate).lstrip("0") or \
        normalize(phone) == normalize(candidate)


class CompatSendMessageView(APIView):
    """POST /messages/send  (httpSMS-compatible).

    Payload: {"content": ..., "from": "+9665...", "to": "+9665..."}
    Auth:    x-api-key: sk_live_...
    """

    permission_classes = [XApiKeyPermission]

    def post(self, request):
        customer, api_key = _customer_from_request(request)
        if customer is None:
            return Response(
                {"errors": ["Invalid API key. Check your httpSMS API key."]},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        content = request.data.get("content")
        to_number = request.data.get("to")
        from_number = request.data.get("from")

        if not to_number or not content:
            return Response(
                {"errors": ["'to' and 'content' are required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from messaging.services.sender import normalize_phone_number
        to_number = normalize_phone_number(str(to_number))

        # Resolve the requested sender SIM (the "from" phone). If one of the
        # customer's SIMs matches, pin the message to that SIM. Otherwise leave
        # selection to the default policy (least used).
        sim_id = None
        if from_number:
            sims = (
                SimCard.objects.filter(
                    device__customer=customer,
                    status=SimCard.Status.ACTIVE,
                    sms_capability=True,
                )
                .select_related("device")
                .order_by("messages_sent")
            )
            matching = next(
                (s for s in sims if _matches_phone(from_number, s.phone_number)),
                None,
            )
            if matching is None:
                return Response(
                    {
                        "errors": [
                            "Sender phone not found. Make sure the httpSMS app has this SIM phone number registered "
                            "and is online."
                        ]
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )
            if not (
                matching.device.status == matching.device.Status.ONLINE
                and matching.device.connection_status == matching.device.ConnectionStatus.CONNECTED
            ):
                return Response(
                    {
                        "errors": [
                            "Gateway phone is offline. Make sure the httpSMS app is running and connected."
                        ]
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            sim_id = str(matching.id)

        try:
            from messaging.models import Message
            message, error = process_single_message(
                customer=customer,
                api_key=api_key,
                to=to_number,
                body=content,
                priority=request.data.get("priority", "NORMAL"),
                sim_id=sim_id,
            )
        except MessageValidationError as exc:
            return Response({"errors": [_detail(exc)]}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("httpSMS send failed")
            return Response(
                {"errors": ["Message could not be sent."]},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "data": {
                    "id": message.public_id,
                    "owner": from_number or "",
                    "from": from_number or "",
                    "to": message.recipient,
                    "content": message.body,
                    "status": message.status,
                }
            },
            status=status.HTTP_200_OK,
        )


class CompatHeartbeatView(APIView):
    """GET /heartbeats?owner=<phone>  (httpSMS-compatible).

    Returns 200 when the configured phone (gateway) is registered, 404 otherwise.
    """

    permission_classes = [XApiKeyPermission]

    def get(self, request):
        customer, api_key = _customer_from_request(request)
        if customer is None:
            return Response(
                {"errors": ["Invalid API key. Check your httpSMS API key."]},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        owner = (request.query_params.get("owner") or request.query_params.get("phone") or "").strip()
        if not owner:
            return Response(
                {"errors": ["Query parameter 'owner' (phone number) is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sims = (
            SimCard.objects.filter(
                device__customer=customer,
                status=SimCard.Status.ACTIVE,
            )
            .select_related("device")
            .order_by("slot")
        )

        matching_sim = next((s for s in sims if _matches_phone(owner, s.phone_number)), None)
        if matching_sim is None:
            return Response(
                {"errors": ["Phone not found. Make sure the httpSMS app is installed and registered."]},
                status=status.HTTP_404_NOT_FOUND,
            )

        device = matching_sim.device
        return Response(
            {
                "data": [
                    {
                        "id": str(device.id),
                        "phone": matching_sim.phone_number,
                        "user": api_key.name if api_key else "",
                        "updated_at": device.last_seen.isoformat() if device.last_seen else timezone.now().isoformat(),
                        "online": device.connection_status == device.ConnectionStatus.CONNECTED,
                        "connection_status": device.connection_status,
                        "is_up_to_date": True,
                    }
                ]
            },
            status=status.HTTP_200_OK,
        )


def _detail(exc):
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict):
        return "; ".join(str(v) for v in detail.values())
    return str(detail)
