from django.urls import path

from webhooks import views

urlpatterns = [
    path("", views.WebhookListCreateView.as_view(), name="webhook_list_create"),
    path("<uuid:pk>/", views.WebhookDetailView.as_view(), name="webhook_detail"),
    path("<uuid:pk>/deliveries/", views.WebhookDeliveriesView.as_view(), name="webhook_deliveries"),
    path("<uuid:pk>/test/", views.WebhookTestView.as_view(), name="webhook_test"),
]