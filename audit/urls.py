from django.urls import path

from audit import views

urlpatterns = [
    path("", views.AuditLogListView.as_view(), name="audit_log_list"),
]