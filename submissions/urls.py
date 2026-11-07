from django.urls import path
from . import views
app_name = 'submissions'
urlpatterns = [
    path('', views.student_dashboard, name='student_dashboard'),
    path('', views.student_dashboard, name='dashboard'),
    path('vao-lop/<str:code>/', views.enter_class, name='enter_class'),
    path('ky-nang/', views.student_home, name='student_home'),
    path('skill/<str:skill>/', views.student_home, name='student_skill'),
    path('lesson/<int:pk>/', views.do_lesson, name='do_lesson'),
    path('lesson/<int:pk>/autosave/', views.autosave, name='lesson_autosave'),
    path('lesson/<int:pk>/autosave/', views.autosave, name='autosave'),
    path('lesson/<int:pk>/submit/', views.submit_lesson, name='submit_lesson'),
    path('tasks/<int:task_id>/', views.do_task, name='do_task'),
    path('tasks/<int:task_id>/audio/', views.lesson_audio, name='lesson_audio'),
    path('tasks/<int:task_id>/video/', views.lesson_video, name='lesson_video'),
    path('tasks/<int:task_id>/questions/<int:question_id>/image/', views.lesson_image, name='lesson_image'),
    path('tasks/<int:task_id>/listening/<int:exercise_id>/<str:kind>/', views.listening_material, name='listening_material'),
    path('tasks/<int:task_id>/draft/', views.autosave, name='autosave'),
    path('results/<int:job_id>/', views.result, name='result'),
]
