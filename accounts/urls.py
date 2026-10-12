from django.urls import path
from accounts import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.user_login_view, name='login'),
    path('logout/', views.user_logout_view, name='logout'),
    path('users/', views.user_list_view, name='user_list'),
    path('users/create/', views.user_create_view, name='user_create'),
    path('users/<int:user_id>/edit/', views.user_update_view, name='user_update'),
    path('users/<int:user_id>/delete/', views.user_delete_view, name='user_delete'),
    path('notifications/', views.notification_list_view, name='notification_list'),
    path('notifications/<int:notification_id>/read/', views.mark_notification_read_view, name='notification_read'),
]
