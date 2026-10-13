from django.urls import path
from . import views

app_name = 'dashboard'
urlpatterns = [path('', views.index, name='index'), path('metrics/', views.metrics, name='metrics')]
