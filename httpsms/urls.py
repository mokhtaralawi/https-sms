"""URL configuration for the SMS Gateway platform."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from dashboard import views as dashboard_views

# Arabic branding for the admin panel header.
admin.site.site_header = "HttpSMS - بوابة إدارة الرسائل"
admin.site.site_title = "HttpSMS"
admin.site.index_title = "لوحة التحكم"

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    # httpSMS-compatible endpoints (root-level, x-api-key auth)
    path("", include("httpsms_compat.urls")),
    # API v1
    path("api/v1/", include("httpsms.api_urls")),
    # Dashboard (could be served by templates in future)
    path("api/v1/dashboard/", include("dashboard.urls")),
    # Schema
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]