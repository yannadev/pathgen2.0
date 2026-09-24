from django.urls import path

from apps.accounts import views


app_name = "account"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("", views.my_account, name="my_account"),
    path("name/", views.update_name, name="update_name"),
    path("password/", views.update_password, name="update_password"),
]

