from django.urls import path

from devices import views

urlpatterns = [
    path("", views.DeviceListCreateView.as_view(), name="device_list_create"),
    path("pair/", views.DevicePairsView.as_view(), name="device_pair"),
    path("<uuid:pk>/", views.DeviceDetailView.as_view(), name="device_detail"),
    path("<uuid:pk>/status/", views.DeviceStatusView.as_view(), name="device_status"),
    path("sims/", views.SimCardListCreateView.as_view(), name="sim_list_create"),
    path("sims/<uuid:pk>/", views.SimCardDetailView.as_view(), name="sim_detail"),
]