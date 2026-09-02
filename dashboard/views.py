from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from api_keys.authentication import APIKeyPrincipal
from core.permissions import IsAdminOrSuper, IsCustomerUserOrBetter
from customers.models import Customer


class DashboardStatsView(APIView):
    permission_classes = [IsCustomerUserOrBetter]

    def get(self, request):
        today = timezone.localdate()
        from messaging.models import Message, IncomingMessage
        from devices.models import Device

        user = request.user
        is_staff = getattr(user, "is_super_admin", False) or getattr(user, "is_admin", False)

        # Determine the customer scope
        if is_staff:
            customer = None
            cid = request.query_params.get("customer_id")
            if cid:
                customer = Customer.objects.filter(id=cid).first()
        elif isinstance(user, APIKeyPrincipal):
            customer = user.customer
        else:
            customer = getattr(user, "customer", None)

        messages = Message.objects.all()
        incoming = IncomingMessage.objects.all()
        devices = Device.objects.all()
        customers = Customer.objects.all()

        if customer:
            messages = messages.filter(customer=customer)
            incoming = incoming.filter(customer=customer)
            devices = devices.filter(customer=customer)

        messages_today = messages.filter(created_at__date=today)
        stats = {
            "messages_today": messages_today.count(),
            "sent": messages_today.filter(status=Message.Status.SENT).count(),
            "delivered": messages_today.filter(status=Message.Status.DELIVERED).count(),
            "failed": messages_today.filter(status=Message.Status.FAILED).count(),
            "incoming": incoming.filter(received_at__date=today).count(),
            "online_devices": devices.filter(status=Device.Status.ONLINE).count(),
            "offline_devices": devices.filter(status=Device.Status.OFFLINE).count(),
            "active_customers": customers.filter(status=Customer.ACTIVE).count(),
            "total_messages": messages.count(),
            "total_devices": devices.count(),
        }
        return Response({"success": True, "stats": stats})


class DashboardRecentMessagesView(APIView):
    permission_classes = [IsCustomerUserOrBetter]

    def get(self, request):
        from messaging.models import Message
        from messaging.serializers import MessageSerializer

        user = request.user
        is_staff = getattr(user, "is_super_admin", False) or getattr(user, "is_admin", False)
        qs = Message.objects.select_related("customer", "device")
        if not is_staff:
            customer = getattr(user, "customer", None)
            if isinstance(user, APIKeyPrincipal):
                customer = user.customer
            if customer:
                qs = qs.filter(customer=customer)
            else:
                qs = qs.none()
        recent = qs.order_by("-created_at")[:20]
        return Response({"success": True, "messages": MessageSerializer(recent, many=True).data})


class DashboardStatusBreakdownView(APIView):
    permission_classes = [IsCustomerUserOrBetter]

    def get(self, request):
        from messaging.models import Message

        user = request.user
        is_staff = getattr(user, "is_super_admin", False) or getattr(user, "is_admin", False)
        qs = Message.objects.all()
        if not is_staff:
            customer = getattr(user, "customer", None)
            if isinstance(user, APIKeyPrincipal):
                customer = user.customer
            qs = qs.filter(customer=customer) if customer else qs.none()

        breakdown = list(qs.values("status").annotate(count=Count("id")))
        return Response({"success": True, "breakdown": breakdown})