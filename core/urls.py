from django.contrib import admin
from django.urls import include, path
from accounts.views import user_login_view
from .views import home

urlpatterns = [
    path('', home),
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('login/', user_login_view, {'template_name':'registration/login.html'}, name='login'),
    path('courses/', include('courses.urls')),
    path('quan-ly/bai-tap/', include('assignments.urls')),
    path('hoc-tap/', include('submissions.urls')),
    path('ai/', include('ai_core.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('ho-tro/', include('support.urls')),
]
