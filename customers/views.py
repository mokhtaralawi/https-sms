from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import AuditLog
from core.permissions import IsAdminOrSuper, IsSuperAdmin
from customers.models import Customer
from customers.serializers import CustomerCreateSerializer, CustomerSerializer, CustomerUpdateSerializer


class CustomerListCreateView(generics.ListCreateAPIView):
    """Admin-only: list & create customers."""
    permission_classes = [IsAdminOrSuper]
    serializer_class = CustomerSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["status", "email"]

    def get_queryset(self):
        return Customer.objects.all()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CustomerCreateSerializer
        return CustomerSerializer

    def perform_create(self, serializer):
        customer = serializer.save()
        AuditLog.objects.create(action="settings.change", user=self.request.user, resource_type="customer",
                                resource_id=str(customer.id), metadata={"action": "create"})


class CustomerDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminOrSuper]
    queryset = Customer.objects.all()
    serializer_class = CustomerUpdateSerializer

    def get_serializer_class(self):
        if self.request.method == "GET":
            return CustomerSerializer
        return CustomerUpdateSerializer


class CustomerStatsView(APIView):
    """Usage/statistics for a customer."""
    permission_classes = [IsAdminOrSuper]

    def get(self, request, pk):
        from usage.models import UsageRecord
        from django.db.models import Count

        customer = Customer.objects.filter(id=pk).first()
        if not customer:
            return Response({"error": "Customer not found"}, status=404)

        messages = customer.messages
        stats = {
            "customer_id": str(customer.id),
            "message_count": messages.count(),
            "incoming_count": customer.incoming_messages.count(),
            "device_count": customer.devices.count(),
            "status_counts": {},
        }
        for status_val, count in messages.values("status").annotate(c=Count("id")):
            stats["status_counts"][status_val] = count
        return Response({"success": True, "stats": stats})


class CustomerToggleStatusView(APIView):
    permission_classes = [IsAdminOrSuper]

    def post(self, request, pk):
        customer = Customer.objects.filter(id=pk).first()
        if not customer:
            return Response({"error": "Customer not found"}, status=404)
        new_status = request.data.get("status")
        valid = {s[0] for s in Customer.STATUS_CHOICES}
        if new_status not in valid:
            return Response({"success": False, "error": "Invalid status"}, status=400)
        customer.status = new_status
        customer.save(update_fields=["status", "updated_at"])
        AuditLog.objects.create(action="settings.change", user=request.user, resource_type="customer",
                                resource_id=str(customer.id), metadata={"field": "status", "value": new_status})
        return Response({"success": True, "customer": CustomerSerializer(customer).data})