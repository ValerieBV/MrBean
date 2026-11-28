from django.urls import path
from . import views

app_name = 'dashboard'
urlpatterns = [
    path('', views.index, name='index'),
    path('metrics/', views.metrics, name='metrics'),
    path('export/', views.export_csv, name='export'),
    path('hoc-vien/<int:learner_id>/', views.index, name='learner'),
    path('hoc-vien/<int:learner_id>/metrics/', views.metrics, name='learner_metrics'),
    path('hoc-vien/<int:learner_id>/export/', views.export_csv, name='learner_export'),
]
