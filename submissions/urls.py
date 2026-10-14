from django.urls import path
from . import views

app_name = "submissions"

urlpatterns = [
    path("", views.student_dashboard, name="dashboard"),
    path("vao-lop/<str:code>/", views.enter_class, name="enter_class"),
    path("ky-nang/", views.student_home, name="student_home"),
    path("skill/<str:skill>/", views.student_skill, name="student_skill"),
    path("lesson/<int:pk>/", views.do_lesson, name="do_lesson"),
    path("lesson/<int:pk>/autosave/", views.autosave, name="autosave"),
    path("lesson/<int:pk>/submit/", views.submit_lesson, name="submit_lesson"),
]
