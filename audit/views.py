from django_filters import rest_framework as filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from api_keys.authentication import APIKeyPrincipal
from audit.models import AuditLog
from audit.serializers import AuditLogSerializer
from core.permissions import IsAdminOrSuper, IsCustomerUserOrBetter


class AuditLogFilter(filters.FilterSet):
    action = filters.CharFilter(field_name="action")
    created_after = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")

    class Meta:
        model = AuditLog
        fields = ["action", "created_after"]


class AuditLogListView(generics.ListAPIView):
    permission_classes = [IsAdminOrSuper]
    serializer_class = AuditLogSerializer
    queryset = AuditLog.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_class = AuditLogFilter