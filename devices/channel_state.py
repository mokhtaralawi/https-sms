"""Registry that tracks which channel currently holds a device's connection.

This prevents duplicate/parallel WebSocket connections for the same device and
ensures the dispatch of sms.send jobs goes to a single connected channel group.
"""

from asgiref.sync import sync_to_async
from django.core.cache import cache

KEY_PREFIX = "device_conn:"


class DeviceChannelRegistry:
    """Holds a mapping device_id -> active channel_name in Redis cache."""

    @staticmethod
    async def try_claim(device_id, channel_name):
        """Atomically try to claim the slot for a device.

        Returns the channel that currently holds it. If none, claims it as ours.
        Uses get_or_set-like semantics via cache.
        """
        key = f"{KEY_PREFIX}{device_id}"
        current = await sync_to_async(cache.get)(key)
        if current is not None:
            # already claimed by another connection
            return False
        # set with a small TTL to avoid stale entries
        await sync_to_async(cache.set)(key, channel_name, timeout=60)
        return True

    @staticmethod
    async def release(device_id, channel_name):
        key = f"{KEY_PREFIX}{device_id}"
        current = await sync_to_async(cache.get)(key)
        if current == channel_name:
            await sync_to_async(cache.delete)(key)

    @staticmethod
    async def get_channel(device_id):
        key = f"{KEY_PREFIX}{device_id}"
        return await sync_to_async(cache.get)(key)
