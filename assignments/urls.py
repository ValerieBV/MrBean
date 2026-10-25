from django.urls import path
from . import views
app_name = 'assignments'
urlpatterns = [
    path('', views.assignment_list, name='assignment_list'),
    path('new/', views.lesson_create, name='lesson_create'),
    path('assign/', views.assign, name='assign'),
    path('lesson/<int:pk>/', views.lesson_detail, name='lesson_detail'),
    path('lesson/<int:pk>/edit/', views.lesson_update, name='lesson_update'),
]
