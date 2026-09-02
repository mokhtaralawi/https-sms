from django.contrib.auth import logout
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from accounts.models import User
from accounts.serializers import ChangePasswordSerializer, CustomerUserCreateSerializer, RegisterSerializer, UserSerializer
from audit.models import AuditLog
from core.permissions import IsSuperAdmin


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_scope = "login"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        AuditLog.objects.create(action="register", user=user, customer=user.customer,
                                metadata={"method": "register"})
        return Response({"success": True, "user": UserSerializer(user).data}, status=status.HTTP_201_CREATED)


class LoginView(TokenObtainPairView):
    throttle_scope = "login"

    def post(self, request, *args, **kwargs):
        from accounts.models import User

        email = request.data.get("email")
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            try:
                user = User.objects.get(email__iexact=email)
                ip = self._client_ip(request)
                user.last_login_ip = ip
                user.save(update_fields=["last_login_ip"])
                AuditLog.objects.create(action="login", user=user, customer=user.customer,
                                        ip_address=ip, metadata={"method": "login"})
            except User.DoesNotExist:
                pass
        return response

    def _client_ip(self, request):
        fwd = request.META.get("HTTP_X_FORWARDED_FOR")
        if fwd:
            return fwd.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh = request.data.get("refresh")
            if refresh:
                token = RefreshToken(refresh)
                token.blacklist()
        except Exception:
            pass
        AuditLog.objects.create(action="logout", user=request.user, customer=getattr(request.user, "customer", None))
        logout(request)
        return Response({"success": True}, status=status.HTTP_200_OK)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"success": True, "user": UserSerializer(request.user).data})


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save()
        AuditLog.objects.create(action="settings.change", user=request.user, metadata={"field": "password"})
        return Response({"success": True})


class UserListView(generics.ListAPIView):
    permission_classes = [IsSuperAdmin]
    queryset = User.objects.select_related("customer").all()
    serializer_class = UserSerializer


class CustomerUserCreateView(generics.CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CustomerUserCreateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        AuditLog.objects.create(action="user.create", user=request.user, customer=getattr(request.user, "customer", None),
                                metadata={"created_email": user.email})
        return Response({"success": True, "user": UserSerializer(user).data}, status=status.HTTP_201_CREATED)
