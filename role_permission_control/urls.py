from django.urls import path
from .views import RoleListAPIView

app_name = "api_roles"

urlpatterns = [
    path("", RoleListAPIView.as_view()),
]