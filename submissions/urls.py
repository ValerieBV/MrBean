from django.urls import path
from . import views
app_name = 'submissions'
urlpatterns = [path('', views.student_dashboard, name='student_dashboard'),
    path('tasks/<int:task_id>/', views.do_task, name='do_task'),
    path('tasks/<int:task_id>/audio/', views.lesson_audio, name='lesson_audio'),
    path('tasks/<int:task_id>/questions/<int:question_id>/image/', views.lesson_image, name='lesson_image'),
    path('tasks/<int:task_id>/draft/', views.autosave, name='autosave'),
    path('results/<int:job_id>/', views.result, name='result')]
