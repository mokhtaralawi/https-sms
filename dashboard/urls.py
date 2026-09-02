from django.urls import path

from dashboard import views

urlpatterns = [
    path("stats/", views.DashboardStatsView.as_view(), name="dashboard_stats"),
    path("recent/", views.DashboardRecentMessagesView.as_view(), name="dashboard_recent"),
    path("status-breakdown/", views.DashboardStatusBreakdownView.as_view(), name="dashboard_status_breakdown"),
]