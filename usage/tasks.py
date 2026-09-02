from celery import shared_task
from django.db.models import Count, Sum
from django.utils import timezone

from core.utils import datetime_now


def record_usage(customer_id, event_type, occurred_at=None, device_id=None, sim_card_id=None,
                 api_key_id=None, message_id=None, count=1, metadata=None):
    """Record a usage event in the background."""
    record_usage_task.delay(
        customer_id=customer_id,
        event_type=event_type,
        occurred_at=occurred_at,
        device_id=device_id,
        sim_card_id=sim_card_id,
        api_key_id=api_key_id,
        message_id=message_id,
        count=count,
        metadata=metadata or {},
    )


@shared_task
def record_usage_task(customer_id, event_type, occurred_at=None, device_id=None, sim_card_id=None,
                      api_key_id=None, message_id=None, count=1, metadata=None):
    from usage.models import UsageRecord

    UsageRecord.objects.create(
        customer_id=customer_id,
        event_type=event_type,
        occurred_at=occurred_at or datetime_now(),
        device_id=device_id,
        sim_card_id=sim_card_id,
        api_key_id=api_key_id,
        message_id=message_id,
        count=count,
        metadata=metadata or {},
    )


@shared_task
def generate_daily_report():
    """Generate/upsert daily usage summaries for the previous day."""
    from django.db.models import Count, Sum
    from django.db import transaction

    from customers.models import Customer
    from usage.models import UsageRecord, UsageSummary

    today = timezone.localdate()
    yesterday = today - timezone.timedelta(days=1)

    customer_ids = Customer.objects.values_list("id", flat=True)
    for cid in customer_ids:
        records = UsageRecord.objects.filter(customer_id=cid, occurred_at__date=yesterday)
        summary, _ = UsageSummary.objects.get_or_create(
            customer_id=cid,
            period=UsageSummary.Period.DAILY,
            period_start=yesterday,
            defaults={"period_end": yesterday},
        )
        summary.sent = records.filter(event_type=UsageRecord.EventType.SENT).count()
        summary.delivered = records.filter(event_type=UsageRecord.EventType.DELIVERED).count()
        summary.failed = records.filter(event_type=UsageRecord.EventType.FAILED).count()
        summary.received = records.filter(event_type=UsageRecord.EventType.RECEIVED).count()
        summary.api_requests = records.filter(event_type=UsageRecord.EventType.API_REQUEST).count()
        summary.period_end = yesterday
        summary.save()
