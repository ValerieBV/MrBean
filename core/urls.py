from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='dashboard:index', permanent=False)),
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('courses/', include('courses.urls')),
    path('quan-ly/bai-tap/', include('assignments.urls')),
    path('hoc-tap/', include('submissions.urls')),
    path('ai/', include('ai_core.urls')),
    path('dashboard/', include('dashboard.urls')),
]
