from django.urls import path

from api_keys import views

urlpatterns = [
    path("", views.APIKeyListCreateView.as_view(), name="api_key_list_create"),
    path("<uuid:pk>/", views.APIKeyDetailView.as_view(), name="api_key_detail"),
    path("<uuid:pk>/revoke/", views.APIKeyRevokeView.as_view(), name="api_key_revoke"),
    path("<uuid:pk>/status/", views.APIKeyStatusView.as_view(), name="api_key_status"),
]