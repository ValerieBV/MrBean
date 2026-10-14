from django.urls import path
from . import views

urlpatterns = [
    path("", views.assignment_list, name="assignment_list"),
    path("skill/<str:skill>/", views.skill_lessons, name="skill_lessons"),
    path("skill/<str:skill>/new/", views.lesson_create, name="lesson_create"),
    path("lesson/<int:pk>/", views.lesson_detail, name="lesson_detail"),
    path("lesson/<int:pk>/edit/", views.lesson_update, name="lesson_update"),
    path("lesson/<int:pk>/delete/", views.lesson_delete, name="lesson_delete"),
    path("item/<str:skill>/<int:pk>/delete/", views.item_delete, name="item_delete"),
]
