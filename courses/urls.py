from django.urls import path
from courses import views

app_name = 'courses'

urlpatterns = [
    path('', views.class_list_view, name='class_list'),
    path('classes/create/', views.class_create_view, name='class_create'),
    path('classes/<int:class_id>/', views.class_detail_view, name='class_detail'),
    path('classes/<int:class_id>/edit/', views.class_update_view, name='class_update'),
    path('classes/<int:class_id>/assign-teacher/', views.assign_teacher_view, name='assign_teacher'),
    path('classes/<int:class_id>/enroll/', views.enroll_student_view, name='enroll_student'),
    path('classes/<int:class_id>/remove/<int:student_id>/', views.remove_student_view, name='remove_student'),
    
    # Miễn BTVN (Listening Only)
    path('classes/<int:class_id>/request-exemption/', views.request_exemption_view, name='request_exemption'),
    path('exemptions/', views.exemption_list_view, name='exemption_list'),
    path('exemptions/<int:exemption_id>/review/', views.exemption_review_view, name='exemption_review'),
]
