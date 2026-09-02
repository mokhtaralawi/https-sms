from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from api_keys.authentication import APIKeyPrincipal
from audit.models import AuditLog
from core.permissions import IsCustomerUserOrBetter
from webhooks.models import Webhook, WebhookDelivery
from webhooks.serializers import (WebhookCreateSerializer, WebhookDeliverySerializer,
                                  WebhookSerializer)


def resolve_customer(request):
    user = request.user
    if isinstance(user, APIKeyPrincipal):
        return user.customer
    if getattr(user, "is_super_admin", False) or getattr(user, "is_admin", False):
        from customers.models import Customer
        cid = request.query_params.get("customer_id") or request.data.get("customer_id")
        return Customer.objects.filter(id=cid).first()
    return getattr(user, "customer", None)


class WebhookListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsCustomerUserOrBetter]
    serializer_class = WebhookSerializer

    def get_queryset(self):
        customer = resolve_customer(self.request)
        if not customer:
            return Webhook.objects.none()
        return Webhook.objects.filter(customer=customer)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return WebhookCreateSerializer
        return WebhookSerializer

    def perform_create(self, serializer):
        customer = resolve_customer(self.request)
        if not customer:
            raise PermissionDenied("No customer context")
        hook = serializer.save(customer=customer)
        AuditLog.objects.create(
            action="webhook.create",
            user=None if isinstance(self.request.user, APIKeyPrincipal) else self.request.user,
            customer=customer, resource_type="webhook", resource_id=str(hook.id))

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        hook = serializer.save(customer=resolve_customer(request))
        # Return the secret once at creation
        data = WebhookSerializer(hook).data
        data["secret"] = hook.secret
        return Response({"success": True, "webhook": data}, status=status.HTTP_201_CREATED)


from rest_framework.exceptions import PermissionDenied  # noqa: E402


class WebhookDetailView(APIView):
    permission_classes = [IsCustomerUserOrBetter]

    def get(self, request, pk):
        customer = resolve_customer(request)
        hook = Webhook.objects.filter(id=pk, customer=customer).first()
        if not hook:
            return Response({"success": False, "error": "Webhook not found"}, status=404)
        return Response({"success": True, "webhook": WebhookSerializer(hook).data})

    def patch(self, request, pk):
        customer = resolve_customer(request)
        hook = Webhook.objects.filter(id=pk, customer=customer).first()
        if not hook:
            return Response({"success": False, "error": "Webhook not found"}, status=404)

        serializer = WebhookCreateSerializer(hook, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"success": True, "webhook": WebhookSerializer(hook).data})

    def delete(self, request, pk):
        customer = resolve_customer(request)
        hook = Webhook.objects.filter(id=pk, customer=customer).first()
        if not hook:
            return Response({"success": False, "error": "Webhook not found"}, status=404)
        hook.delete()
        return Response({"success": True})


class WebhookDeliveriesView(APIView):
    permission_classes = [IsCustomerUserOrBetter]

    def get(self, request, pk):
        customer = resolve_customer(request)
        hook = Webhook.objects.filter(id=pk, customer=customer).first()
        if not hook:
            return Response({"success": False, "error": "Webhook not found"}, status=404)
        deliveries = WebhookDelivery.objects.filter(webhook=hook)[:100]
        return Response({"success": True, "deliveries": WebhookDeliverySerializer(deliveries, many=True).data})


class WebhookTestView(APIView):
    permission_classes = [IsCustomerUserOrBetter]

    def post(self, request, pk):
        customer = resolve_customer(request)
        hook = Webhook.objects.filter(id=pk, customer=customer).first()
        if not hook:
            return Response({"success": False, "error": "Webhook not found"}, status=404)

        from webhooks.tasks import send_webhook
        from webhooks.models import WebhookDelivery

        delivery = WebhookDelivery.objects.create(
            webhook=hook,
            customer=customer,
            event="test",
            payload={"ping": "pong"},
            idempotency_key=f"test:{pk}",
            status=WebhookDelivery.Status.PENDING,
        )
        send_webhook.delay(str(delivery.id))
        return Response({"success": True, "delivery_id": str(delivery.id)})