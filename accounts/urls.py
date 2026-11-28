from django.urls import path
from accounts import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.user_login_view, name='login'),
    path('logout/', views.user_logout_view, name='logout'),
    path('profile/', views.profile, name='profile'),
    path('password/', views.password_change, name='password_change'),
    path('users/', views.user_list_view, name='user_list'),
    path('users/create/', views.user_create_view, name='user_create'),
    path('users/<int:user_id>/edit/', views.user_update_view, name='user_update'),
    path('users/<int:user_id>/delete/', views.user_delete_view, name='user_delete'),
    path('users/<int:user_id>/deactivate/', views.user_deactivate_view, name='user_deactivate'),
    path('users/<int:user_id>/password/', views.password_reset_user, name='password_reset'),
    path('notifications/', views.notification_list_view, name='notification_list'),
    path('notifications/read-all/', views.notifications_read_all, name='notifications_read_all'),
    path('notifications/<int:notification_id>/read/', views.mark_notification_read_view, name='notification_read'),
]
