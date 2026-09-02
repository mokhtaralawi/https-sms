from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from accounts import views

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="register"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("verify/", TokenVerifyView.as_view(), name="token_verify"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.MeView.as_view(), name="me"),
    path("change-password/", views.ChangePasswordView.as_view(), name="change_password"),
    path("users/", views.UserListView.as_view(), name="user_list"),
    path("users/create/", views.CustomerUserCreateView.as_view(), name="customer_user_create"),
]
