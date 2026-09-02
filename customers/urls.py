from django.urls import path

from customers import views

urlpatterns = [
    path("", views.CustomerListCreateView.as_view(), name="customer_list_create"),
    path("<uuid:pk>/", views.CustomerDetailView.as_view(), name="customer_detail"),
    path("<uuid:pk>/stats/", views.CustomerStatsView.as_view(), name="customer_stats"),
    path("<uuid:pk>/status/", views.CustomerToggleStatusView.as_view(), name="customer_status"),
]