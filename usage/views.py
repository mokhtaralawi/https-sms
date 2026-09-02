import calendar
from datetime import date, timedelta

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api_keys.authentication import APIKeyPrincipal
from core.permissions import IsAdminOrSuper, IsCustomerUserOrBetter
from usage.models import UsageRecord, UsageSummary


def resolve_customer(request):
    user = request.user
    if isinstance(user, APIKeyPrincipal):
        return user.customer
    if getattr(user, "is_super_admin", False) or getattr(user, "is_admin", False):
        from customers.models import Customer
        cid = request.query_params.get("customer_id")
        return Customer.objects.filter(id=cid).first()
    return getattr(user, "customer", None)


class UsageListView(APIView):
    permission_classes = [IsCustomerUserOrBetter]

    def get(self, request):
        customer = resolve_customer(request)
        if not customer:
            return Response({"success": False, "error": "No customer context"}, status=403)

        start = request.query_params.get("start")
        end = request.query_params.get("end")
        event_type = request.query_params.get("event_type")
        device_id = request.query_params.get("device_id")
        sim_id = request.query_params.get("sim_id")

        qs = UsageRecord.objects.filter(customer=customer)
        if start:
            qs = qs.filter(occurred_at__date__gte=start)
        if end:
            qs = qs.filter(occurred_at__date__lte=end)
        if event_type:
            qs = qs.filter(event_type=event_type)
        if device_id:
            qs = qs.filter(device_id=device_id)
        if sim_id:
            qs = qs.filter(sim_card_id=sim_id)

        qs = qs.order_by("-occurred_at")

        from rest_framework.pagination import PageNumberPagination
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            from usage.serializers import UsageRecordSerializer
            data = UsageRecordSerializer(page, many=True).data
            return paginator.get_paginated_response({"success": True, "usage": data})

        from usage.serializers import UsageRecordSerializer
        return Response({"success": True, "usage": UsageRecordSerializer(qs, many=True).data})


class UsageSummaryView(APIView):
    permission_classes = [IsCustomerUserOrBetter]

    def get(self, request):
        customer = resolve_customer(request)
        if not customer:
            return Response({"success": False, "error": "No customer context"}, status=403)

        period = request.query_params.get("period", "DAILY")
        start = request.query_params.get("start") or (timezone.localdate() - timedelta(days=30)).isoformat()
        end = request.query_params.get("end") or timezone.localdate().isoformat()

        qs = UsageSummary.objects.filter(
            customer=customer, period=period, period_start__gte=start, period_start__lte=end
        ).order_by("period_start")

        return Response({"success": True, "summaries": list(qs.values(
            "period", "period_start", "period_end", "sent", "delivered", "failed", "received", "api_requests"
        ))})


class UsageTotalsView(APIView):
    permission_classes = [IsCustomerUserOrBetter]

    def get(self, request):
        customer = resolve_customer(request)
        if not customer:
            return Response({"success": False, "error": "No customer context"}, status=403)

        today = timezone.localdate()
        start = request.query_params.get("start") or (today - timedelta(days=30)).isoformat()
        end = request.query_params.get("end") or today.isoformat()

        qs = UsageRecord.objects.filter(customer=customer, occurred_at__date__gte=start, occurred_at__date__lte=end)

        totals = {
            "sent": qs.filter(event_type="SENT").count(),
            "delivered": qs.filter(event_type="DELIVERED").count(),
            "failed": qs.filter(event_type="FAILED").count(),
            "received": qs.filter(event_type="RECEIVED").count(),
            "api_requests": qs.filter(event_type="API_REQUEST").count(),
        }

        by_device = (
            UsageRecord.objects.filter(customer=customer, occurred_at__date__gte=start, occurred_at__date__lte=end)
            .exclude(device_id__isnull=True)
            .values("device_id")
            .annotate(total=Count("id"))
            .order_by("-total")
        )
        by_sim = (
            UsageRecord.objects.filter(customer=customer, occurred_at__date__gte=start, occurred_at__date__lte=end)
            .exclude(sim_card_id__isnull=True)
            .values("sim_card_id")
            .annotate(total=Count("id"))
            .order_by("-total")
        )

        return Response({
            "success": True,
            "total": totals,
            "by_device": list(by_device),
            "by_sim": list(by_sim),
            "start": start,
            "end": end,
        })


class UsageDailyTimelineView(APIView):
    permission_classes = [IsAdminOrSuper]

    def get(self, request):
        """Admin view: aggregate usage across all customers over time."""
        start = request.query_params.get("start") or (timezone.localdate() - timedelta(days=14)).isoformat()
        end = request.query_params.get("end") or timezone.localdate().isoformat()

        summaries = (
            UsageSummary.objects.filter(period_start__gte=start, period_start__lte=end)
            .values("period_start")
            .annotate(
                total_sent=Sum("sent"),
                total_delivered=Sum("delivered"),
                total_failed=Sum("failed"),
                total_received=Sum("received"),
                total_api=Sum("api_requests"),
            )
            .order_by("period_start")
        )
        return Response({"success": True, "timeline": list(summaries)})