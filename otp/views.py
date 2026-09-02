from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api_keys.authentication import APIKeyPrincipal
from core.permissions import IsCustomerUserOrBetter
from otp.serializers import OTPSendSerializer, OTPVerifySerializer
from otp.services import OTPError, OTPService


def get_customer(request):
    user = request.user
    if isinstance(user, APIKeyPrincipal):
        return user.customer
    return getattr(user, "customer", None)


class OTPSendView(APIView):
    permission_classes = [IsCustomerUserOrBetter]
    throttle_scope = "otp"

    def post(self, request):
        customer = get_customer(request)
        if not customer:
            return Response({"success": False, "error": "No customer context"}, status=403)
        serializer = OTPSendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = OTPService.send(customer, serializer.validated_data["to"],
                                     purpose=serializer.validated_data.get("purpose", "authentication"))
        except OTPError as exc:
            return Response({"success": False, "error": str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        return Response({"success": True, "otp_id": result["otp_id"], "message_id": result["message_id"]},
                        status=status.HTTP_202_ACCEPTED)


class OTPVerifyView(APIView):
    permission_classes = [IsCustomerUserOrBetter]
    throttle_scope = "otp"

    def post(self, request):
        customer = get_customer(request)
        if not customer:
            return Response({"success": False, "error": "No customer context"}, status=403)
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ok = OTPService.verify(
                customer,
                serializer.validated_data["to"],
                serializer.validated_data["code"],
                otp_id=serializer.validated_data.get("otp_id"),
                purpose=serializer.validated_data.get("purpose", "authentication"),
            )
        except OTPError as exc:
            return Response({"success": False, "error": str(exc)}, status=400)
        if ok:
            return Response({"success": True, "verified": True})
        return Response({"success": False, "verified": False, "error": "Invalid or expired code."},
                        status=status.HTTP_400_BAD_REQUEST)