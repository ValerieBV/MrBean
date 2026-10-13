from django.urls import path
from . import views

urlpatterns = [
    path("", views.assignment_list, name="assignment_list"),
    path("create/", views.assignment_create, name="assignment_create"),
    path("<int:pk>/edit/", views.assignment_update, name="assignment_update"),
    path("<int:pk>/delete/", views.assignment_delete, name="assignment_delete"),
]
