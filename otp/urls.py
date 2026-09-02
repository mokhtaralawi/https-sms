from django.urls import path

from otp import views

urlpatterns = [
    path("send/", views.OTPSendView.as_view(), name="otp_send"),
    path("verify/", views.OTPVerifyView.as_view(), name="otp_verify"),
]