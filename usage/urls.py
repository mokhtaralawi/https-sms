from django.urls import path

from usage import views

urlpatterns = [
    path("", views.UsageListView.as_view(), name="usage_list"),
    path("summary/", views.UsageSummaryView.as_view(), name="usage_summary"),
    path("totals/", views.UsageTotalsView.as_view(), name="usage_totals"),
    path("timeline/", views.UsageDailyTimelineView.as_view(), name="usage_timeline"),
]