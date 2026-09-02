import hashlib
import logging

from django.core.cache import cache
from django_filters import rest_framework as filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from api_keys.authentication import APIKeyPrincipal
from core.permissions import IsCustomerUserOrBetter
from messaging.models import IncomingMessage, Message
from messaging.serializers import (IncomingMessageSerializer, MessageAttemptSerializer,
                                   MessageBulkCreateSerializer, MessageCancelSerializer,
                                   MessageCreateSerializer, MessageSerializer)
from messaging.services.sender import MessageValidationError, process_bulk_message, process_single_message
from usage.tasks import record_usage
from audit.models import AuditLog

logger = logging.getLogger("httpsms.messaging")


class MessageFilter(filters.FilterSet):
    status = filters.CharFilter(field_name="status")
    recipient = filters.CharFilter(field_name="recipient")
    created_after = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Message
        fields = ["status", "recipient", "created_after", "created_before"]


def get_customer_from_request(request):
    """Returns (customer, api_key) for the authenticated principal."""
    user = request.user
    if isinstance(user, APIKeyPrincipal):
        return user.customer, user.api_key
    if getattr(user, "customer_id", None):
        return user.customer, None
    return None, None


def enforce_limits(request, customer):
    from core.services.rate_limit import rate_limiter
    allowed, metric = rate_limiter.check_customer_limits(customer)
    if not allowed:
        from rest_framework.exceptions import Throttled
        raise Throttled(detail=f"Rate limit exceeded: {metric}")


class MessageListCreateView(APIView):
    permission_classes = [IsCustomerUserOrBetter]

    def get(self, request):
        customer, _ = get_customer_from_request(request)
        if not customer:
            return Response({"success": False, "error": "No customer context"}, status=403)

        qs = Message.objects.filter(customer=customer).select_related("device", "sim_card")
        qs = MessageFilter(request.query_params, queryset=qs).qs.order_by("-created_at")

        # Pagination
        from rest_framework.pagination import PageNumberPagination

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            data = MessageSerializer(page, many=True).data
            return Response({
                "success": True,
                "count": paginator.page.paginator.count,
                "next": paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
                "messages": data,
            })
        return Response({"success": True, "messages": MessageSerializer(qs, many=True).data})

    def post(self, request):
        """POST /api/v1/messages/  -- single SMS send"""
        customer, api_key = get_customer_from_request(request)
        if not customer:
            return Response({"success": False, "error": "No customer context"}, status=403)

        serializer = MessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Idempotency
        idempotency_key = request.headers.get("Idempotency-Key") or request.data.get("idempotency_key")
        if idempotency_key:
            existing = Message.objects.filter(customer=customer, idempotency_key=idempotency_key).first()
            if existing:
                return Response({
                    "success": True,
                    "message_id": existing.public_id,
                    "status": existing.status,
                    "duplicate": True,
                }, status=status.HTTP_200_OK)

        try:
            message, error = process_single_message(
                customer=customer,
                api_key=api_key,
                to=serializer.validated_data["to"],
                body=serializer.validated_data["message"],
                priority=serializer.validated_data.get("priority", "NORMAL"),
                scheduled_at=serializer.validated_data.get("scheduled_at"),
                expires_at=serializer.validated_data.get("expires_at"),
                idempotency_key=idempotency_key,
                max_attempts=serializer.validated_data.get("max_attempts"),
                device_id=serializer.validated_data.get("device_id"),
                sim_id=serializer.validated_data.get("sim_id"),
            )
        except MessageValidationError as exc:
            return Response({"success": False, "error": exc.detail}, status=400)
        except APIException as exc:
            return Response({"success": False, "error": str(exc.detail)}, status=exc.status_code)

        AuditLog.objects.create(
            action="message.create",
            user=None if isinstance(request.user, APIKeyPrincipal) else request.user,
            customer=customer, resource_type="message", resource_id=str(message.id))

        return Response({
            "success": True,
            "message_id": message.public_id,
            "status": "queued",
            "duplicate": False,
        }, status=status.HTTP_201_CREATED)


class MessageBulkView(APIView):
    permission_classes = [IsCustomerUserOrBetter]

    def post(self, request):
        """POST /api/v1/messages/bulk/  -- bulk SMS send"""
        customer, api_key = get_customer_from_request(request)
        if not customer:
            return Response({"success": False, "error": "No customer context"}, status=403)

        serializer = MessageBulkCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        idempotency_key = request.headers.get("Idempotency-Key") or request.data.get("idempotency_key")
        if idempotency_key:
            existing = Message.objects.filter(customer=customer, idempotency_key=idempotency_key).exclude(
                bulk_group_id__isnull=True).first()
            if existing:
                count = Message.objects.filter(customer=customer, bulk_group_id=existing.bulk_group_id).count()
                return Response({
                    "success": True,
                    "bulk_group_id": str(existing.bulk_group_id),
                    "count": count,
                    "status": "queued",
                    "duplicate": True,
                })

        try:
            messages, bulk_group_id, error = process_bulk_message(
                customer=customer,
                api_key=api_key,
                recipients=serializer.validated_data["recipients"],
                body=serializer.validated_data["message"],
                priority=serializer.validated_data.get("priority", "NORMAL"),
                expires_at=serializer.validated_data.get("expires_at"),
                idempotency_key=idempotency_key,
            )
        except MessageValidationError as exc:
            return Response({"success": False, "error": exc.detail}, status=400)

        record_usage(str(customer.id), "API_REQUEST", api_key_id=str(api_key.id) if api_key else None,
                     metadata={"bulk": True, "count": len(messages)})

        return Response({
            "success": True,
            "bulk_group_id": str(messages[0].bulk_group_id) if messages else None,
            "count": len(messages),
            "status": "queued",
        }, status=status.HTTP_202_ACCEPTED)


class MessageDetailView(APIView):
    permission_classes = [IsCustomerUserOrBetter]

    def get_object(self, request, public_id):
        customer, _ = get_customer_from_request(request)
        return Message.objects.filter(customer=customer, public_id=public_id).first()

    def get(self, request, public_id):
        message = self.get_object(request, public_id)
        if not message:
            return Response({"success": False, "error": "Message not found"}, status=404)
        return Response({"success": True, "message": MessageSerializer(message).data})

    def delete(self, request, public_id):
        """Cancel a queued message."""
        message = self.get_object(request, public_id)
        if not message:
            return Response({"success": False, "error": "Message not found"}, status=404)
        if message.status not in [Message.Status.QUEUED, Message.Status.ASSIGNED]:
            return Response({"success": False, "error": "Message can only be cancelled while queued."}, status=400)

        customer_id = str(message.customer_id)
        message.transition(Message.Status.CANCELLED)
        message.save()
        from webhooks.tasks import fire_webhook_event
        fire_webhook_event.delay(customer_id, "message.failed", {"message_id": message.public_id})
        return Response({"success": True, "message": MessageSerializer(message).data})


class MessageAttemptsView(APIView):
    permission_classes = [IsCustomerUserOrBetter]

    def get(self, request, public_id):
        customer, _ = get_customer_from_request(request)
        message = Message.objects.filter(customer=customer, public_id=public_id).first()
        if not message:
            return Response({"success": False, "error": "Message not found"}, status=404)
        attempts = message.attempt_records.all()
        return Response({"success": True, "message_id": message.public_id,
                         "attempts": MessageAttemptSerializer(attempts, many=True).data})


class IncomingMessageListView(APIView):
    permission_classes = [IsCustomerUserOrBetter]

    def get(self, request):
        customer, _ = get_customer_from_request(request)
        if not customer:
            return Response({"success": False, "error": "No customer context"}, status=403)
        qs = IncomingMessage.objects.filter(customer=customer).order_by("-received_at")
        from rest_framework.pagination import PageNumberPagination
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            data = IncomingMessageSerializer(page, many=True).data
            return Response({
                "success": True,
                "count": paginator.page.paginator.count,
                "next": paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
                "messages": data,
            })
        return Response({"success": True, "messages": IncomingMessageSerializer(qs, many=True).data})


class IncomingMessageDetailView(APIView):
    permission_classes = [IsCustomerUserOrBetter]

    def get(self, request, public_id):
        customer, _ = get_customer_from_request(request)
        message = IncomingMessage.objects.filter(customer=customer, public_id=public_id).first()
        if not message:
            return Response({"success": False, "error": "Message not found"}, status=404)
        return Response({"success": True, "message": IncomingMessageSerializer(message).data})