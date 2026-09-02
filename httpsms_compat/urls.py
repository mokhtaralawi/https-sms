from django.urls import path

from httpsms_compat import views

urlpatterns = [
    path("messages/send", views.CompatSendMessageView.as_view(), name="compat_messages_send"),
    path("heartbeats", views.CompatHeartbeatView.as_view(), name="compat_heartbeats"),
]
