import secrets

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from api_keys.authentication import APIKeyPrincipal
from audit.models import AuditLog
from core.permissions import IsAdminOrSuper, IsCustomerUserOrBetter
from devices.models import Device, SimCard
from devices.serializers import (DeviceRegisterSerializer, DeviceSerializer,
                                 SimCardSerializer)


def resolve_customer(request):
    user = request.user
    if isinstance(user, APIKeyPrincipal):
        return user.customer
    if getattr(user, "is_super_admin", False) or getattr(user, "is_admin", False):
        from customers.models import Customer
        cid = request.query_params.get("customer_id") or request.data.get("customer_id")
        return Customer.objects.filter(id=cid).first()
    return getattr(user, "customer", None)


class DeviceListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsCustomerUserOrBetter]
    serializer_class = DeviceSerializer

    def get_queryset(self):
        customer = resolve_customer(self.request)
        if not customer:
            return Device.objects.none()
        qs = Device.objects.filter(customer=customer).prefetch_related("sim_cards")
        return qs

    def perform_create(self, serializer):
        customer = resolve_customer(self.request)
        device = serializer.save(customer=customer)
        AuditLog.objects.create(
            action="device.register",
            user=None if isinstance(self.request.user, APIKeyPrincipal) else self.request.user,
            customer=customer, resource_type="device", resource_id=str(device.id))


class DeviceDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsCustomerUserOrBetter]
    queryset = Device.objects.all()
    serializer_class = DeviceSerializer

    def get_object(self):
        device = super().get_object()
        customer = resolve_customer(self.request)
        staff = getattr(self.request.user, "is_super_admin", False) or getattr(self.request.user, "is_admin", False)
        if not staff and (not customer or device.customer_id != customer.id):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You don't have access to this device.")
        return device


class DevicePairsView(APIView):
    """Issue a pairing token + uuid for a new Android device."""
    permission_classes = [IsCustomerUserOrBetter]

    def post(self, request):
        customer = resolve_customer(request)
        if not customer:
            return Response({"success": False, "error": "No customer context"}, status=403)

        serializer = DeviceRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token = secrets.token_urlsafe(32)
        device = Device.objects.create(
            customer=customer,
            name=serializer.validated_data.get("name", "Android Gateway"),
            model=serializer.validated_data.get("model", ""),
            manufacturer=serializer.validated_data.get("manufacturer", ""),
            android_version=serializer.validated_data.get("android_version", ""),
            auth_token=token,
            status=Device.Status.OFFLINE,
        )
        phone_number = (serializer.validated_data.get("phone_number") or "").strip()
        if phone_number:
            SimCard.objects.update_or_create(
                device=device,
                slot=0,
                defaults={
                    "phone_number": phone_number,
                    "status": SimCard.Status.ACTIVE,
                },
            )
        AuditLog.objects.create(action="device.register",
                                user=None if isinstance(request.user, APIKeyPrincipal) else request.user,
                                customer=customer, resource_type="device", resource_id=str(device.id))
        return Response({
            "success": True,
            "device": {
                "id": str(device.id),
                "device_uuid": str(device.device_uuid),
                "token": token,
                "websocket_url": "/ws/device/",
            }
        }, status=status.HTTP_201_CREATED)


class DeviceStatusView(APIView):
    permission_classes = [IsCustomerUserOrBetter]

    def get(self, request, pk):
        customer = resolve_customer(request)
        device = Device.objects.filter(id=pk).first()
        staff = getattr(request.user, "is_super_admin", False) or getattr(request.user, "is_admin", False)
        if not device or (not staff and device.customer_id != (customer.id if customer else None)):
            return Response({"success": False, "error": "Device not found"}, status=404)
        return Response({"success": True, "device": DeviceSerializer(device).data})

    def post(self, request, pk):
        """Suspend / block / activate a device."""
        customer = resolve_customer(request)
        device = Device.objects.filter(id=pk).first()
        staff = getattr(request.user, "is_super_admin", False) or getattr(request.user, "is_admin", False)
        if not device or (not staff and device.customer_id != (customer.id if customer else None)):
            return Response({"success": False, "error": "Device not found"}, status=404)
        new_status = request.data.get("status")
        valid = {s[0] for s in Device.Status.choices}
        if new_status not in valid:
            return Response({"success": False, "error": "Invalid status"}, status=400)
        device.status = new_status
        device.save(update_fields=["status", "updated_at"])
        AuditLog.objects.create(action="settings.change",
                                user=None if isinstance(request.user, APIKeyPrincipal) else request.user,
                                customer=customer, resource_type="device", resource_id=str(device.id),
                                metadata={"field": "status", "value": new_status})
        return Response({"success": True, "device": DeviceSerializer(device).data})


class SimCardListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsCustomerUserOrBetter]
    serializer_class = SimCardSerializer

    def get_queryset(self):
        customer = resolve_customer(self.request)
        if not customer:
            return SimCard.objects.none()
        return SimCard.objects.filter(device__customer=customer)

    def perform_create(self, serializer):
        customer = resolve_customer(self.request)
        device = serializer.validated_data["device"]
        staff = getattr(self.request.user, "is_super_admin", False) or getattr(self.request.user, "is_admin", False)
        if not staff and device.customer_id != customer.id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Device not in your customer.")
        serializer.save()


class SimCardDetailView(APIView):
    permission_classes = [IsCustomerUserOrBetter]

    def get_object(self, request, pk):
        customer = resolve_customer(request)
        sim = SimCard.objects.filter(id=pk).first()
        staff = getattr(request.user, "is_super_admin", False) or getattr(request.user, "is_admin", False)
        if not sim or (not staff and sim.device.customer_id != (customer.id if customer else None)):
            return None
        return sim

    def get(self, request, pk):
        sim = self.get_object(request, pk)
        if not sim:
            return Response({"success": False, "error": "SIM not found"}, status=404)
        return Response({"success": True, "sim_card": SimCardSerializer(sim).data})

    def patch(self, request, pk):
        sim = self.get_object(request, pk)
        if not sim:
            return Response({"success": False, "error": "SIM not found"}, status=404)
        serializer = SimCardSerializer(sim, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"success": True, "sim_card": SimCardSerializer(sim).data})