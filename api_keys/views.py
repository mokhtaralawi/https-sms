from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from api_keys.authentication import APIKeyPrincipal
from api_keys.models import APIKey
from api_keys.serializers import APIKeyCreateSerializer, APIKeyRevokeSerializer, APIKeySerializer
from audit.models import AuditLog
from core.permissions import IsAdminOrSuper, IsCustomerUserOrBetter


def resolve_customer(request, customer_id=None):
    """Resolve which customer an API key belongs to."""
    user = request.user
    if isinstance(user, APIKeyPrincipal):
        if customer_id is not None and str(user.customer.id) != str(customer_id):
            raise PermissionDenied("Not allowed to access another customer.")
        return user.customer

    if getattr(user, "is_super_admin", False) or getattr(user, "is_admin", False):
        from customers.models import Customer
        if customer_id is None:
            raise PermissionDenied("customer_id is required for staff.")
        customer = Customer.objects.filter(id=customer_id).first()
        if not customer:
            raise PermissionDenied("Customer not found.")
        return customer

    # Customer or customer_user
    if not getattr(user, "customer_id", None):
        raise PermissionDenied("No customer associated with your account.")
    return user.customer


class APIKeyListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsCustomerUserOrBetter]
    serializer_class = APIKeySerializer

    def get_serializer_class(self):
        if self.request.method == "POST":
            return APIKeyCreateSerializer
        return APIKeySerializer

    def get_queryset(self):
        customer = resolve_customer(self.request, self.request.query_params.get("customer_id"))
        qs = APIKey.objects.filter(customer=customer).select_related("customer")
        if self.request.query_params.get("environment"):
            qs = qs.filter(environment=self.request.query_params.get("environment"))
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params.get("status"))
        return qs

    def perform_create(self, serializer):
        customer = resolve_customer(self.request, self.request.data.get("customer_id"))
        if customer.status != "ACTIVE":
            raise PermissionDenied("Customer is not active.")

        api_key, raw = APIKey.create_for_customer(
            customer=customer,
            name=serializer.validated_data["name"],
            environment=serializer.validated_data.get("environment", "LIVE"),
            expires_in_days=serializer.validated_data.get("expires_at"),
        )
        # Attach raw key so the serializer surfaces it this one time
        api_key._raw_key = raw
        AuditLog.objects.create(
            action="api_key.create",
            user=None if isinstance(self.request.user, APIKeyPrincipal) else self.request.user,
            customer=customer, resource_type="apikey", resource_id=str(api_key.id),
            metadata={"name": api_key.name, "environment": api_key.environment})

        # Serialize with custom response that includes the key once.
        data = APIKeySerializer(api_key).data
        data["key"] = raw
        self.response_data = data

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response({"success": True, "api_key": self.response_data}, status=status.HTTP_201_CREATED)


class APIKeyDetailView(APIView):
    permission_classes = [IsCustomerUserOrBetter]

    def get(self, request, pk):
        customer = resolve_customer(request, request.query_params.get("customer_id"))
        key = APIKey.objects.filter(id=pk, customer=customer).first()
        if not key:
            return Response({"success": False, "error": "API key not found"}, status=404)
        return Response({"success": True, "api_key": APIKeySerializer(key).data})


class APIKeyRevokeView(APIView):
    permission_classes = [IsCustomerUserOrBetter]

    def post(self, request, pk):
        customer = resolve_customer(request, request.data.get("customer_id"))
        key = APIKey.objects.filter(id=pk, customer=customer).first()
        if not key:
            return Response({"success": False, "error": "API key not found"}, status=404)
        if key.status == APIKey.Status.REVOKED:
            return Response({"success": False, "error": "API key already revoked"}, status=400)
        key.revoke()
        AuditLog.objects.create(
            action="api_key.revoke",
            user=None if isinstance(self.request.user, APIKeyPrincipal) else self.request.user,
            customer=customer, resource_type="apikey", resource_id=str(key.id),
            metadata={"revoked_at": key.revoked_at.isoformat()})
        return Response({"success": True, "api_key": APIKeySerializer(key).data})


class APIKeyStatusView(APIView):
    permission_classes = [IsCustomerUserOrBetter]

    def get(self, request, pk):
        customer = resolve_customer(request, request.query_params.get("customer_id"))
        key = APIKey.objects.filter(id=pk, customer=customer).first()
        if not key:
            return Response({"success": False, "error": "API key not found"}, status=404)
        return Response({"success": True, "active": key.is_active})