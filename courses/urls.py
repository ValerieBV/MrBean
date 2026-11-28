from django.urls import path
from . import views
app_name = 'courses'
urlpatterns = [
    path('', views.class_list_view, name='class_list'),
    path('catalog/', views.course_list, name='course_list'),
    path('catalog/new/', views.course_form, name='course_create'),
    path('catalog/<int:pk>/edit/', views.course_form, name='course_update'),
    path('catalog/<int:pk>/delete/', views.course_delete, name='course_delete'),
    path('classes/create/', views.class_create_view, name='class_create'),
    path('enrollments/<int:pk>/edit/', views.enrollment_update, name='enrollment_update'),
    path('classes/<int:class_id>/', views.class_detail_view, name='class_detail'),
    path('classes/<int:class_id>/edit/', views.class_update_view, name='class_update'),
    path('classes/<int:class_id>/assign-teacher/', views.assign_teacher_view, name='assign_teacher'),
    path('classes/<int:class_id>/enroll/', views.enroll_student_view, name='enroll_student'),
    path('classes/<int:class_id>/remove/<int:student_id>/', views.remove_student_view, name='remove_student'),
    path('classes/<int:class_id>/request-exemption/', views.request_exemption_view, name='request_exemption'),
    path('exemptions/', views.exemption_list_view, name='exemption_list'),
    path('exemptions/<int:exemption_id>/review/', views.exemption_review_view, name='exemption_review'),
    path('exemptions/<int:exemption_id>/cancel/', views.exemption_cancel, name='exemption_cancel'),
]
