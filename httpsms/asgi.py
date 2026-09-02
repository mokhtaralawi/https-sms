"""
ASGI config for httpsms project.

Exposes both the HTTP application and the combined ASGI application
that routes WebSocket connections to Django Channels.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "httpsms.settings")

# Initialize Django before importing channels routing
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from devices.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            URLRouter(websocket_urlpatterns)
        ),
    }
)
