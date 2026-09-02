from django.urls import path

from messaging import views

urlpatterns = [
    path("", views.MessageListCreateView.as_view(), name="message_list_create"),
    path("bulk/", views.MessageBulkView.as_view(), name="message_bulk"),
    path("incoming/", views.IncomingMessageListView.as_view(), name="incoming_message_list"),
    path("incoming/<str:public_id>/", views.IncomingMessageDetailView.as_view(), name="incoming_message_detail"),
    path("<str:public_id>/attempts/", views.MessageAttemptsView.as_view(), name="message_attempts"),
    path("<str:public_id>/", views.MessageDetailView.as_view(), name="message_detail"),
]