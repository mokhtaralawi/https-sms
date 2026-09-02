from django.urls import include, path

urlpatterns = [
    path("auth/", include("accounts.urls")),
    path("customers/", include("customers.urls")),
    path("api-keys/", include("api_keys.urls")),
    path("devices/", include("devices.urls")),
    path("messages/", include("messaging.urls")),
    path("webhooks/", include("webhooks.urls")),
    path("otp/", include("otp.urls")),
    path("usage/", include("usage.urls")),
    path("audit/", include("audit.urls")),
]