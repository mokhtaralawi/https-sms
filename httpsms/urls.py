"""URL configuration for the SMS Gateway platform."""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from dashboard import views as dashboard_views

urlpatterns = [
    path("admin/", admin.site.urls),
    # API v1
    path("api/v1/", include("httpsms.api_urls")),
    # Dashboard (could be served by templates in future)
    path("api/v1/dashboard/", include("dashboard.urls")),
    # Schema
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]