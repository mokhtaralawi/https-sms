from datetime import timedelta

from celery import shared_task
from django.utils import timezone


@shared_task
def mark_offline_devices():
    from devices.models import Device

    cutoff = timezone.now() - timedelta(seconds=90)
    stale = Device.objects.filter(last_seen__lte=cutoff, status=Device.Status.ONLINE)
    count = 0
    for device in stale:
        device.mark_offline()
        count += 1
    return count
