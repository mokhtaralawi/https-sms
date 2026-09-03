from django.urls import path

from webapp import views

app_name = "webapp"

urlpatterns = [
    path("", views.index_view, name="index"),
    path("register/", views.register_view, name="register"),
    path("otp/", views.otp_view, name="otp"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("google/login/", views.google_login, name="google_login"),
    path("google/callback/", views.google_callback, name="google_callback"),
]
