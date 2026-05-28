from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("projectRepo.urls")),
]

if settings.DEBUG:
    if getattr(settings, 'MEDIA_URL', None) and getattr(settings, 'MEDIA_ROOT', None):
        urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    if getattr(settings, 'STATIC_URL', None) and getattr(settings, 'STATIC_ROOT', None):
        urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

handler403 = "projectRepo.views.error_403"
handler404 = "projectRepo.views.error_404"
handler500 = "projectRepo.views.error_500"