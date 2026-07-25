from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.decorators.cache import cache_control
from django.views.static import serve


@cache_control(private=True, max_age=31536000, immutable=True)
def serve_media(request, path):
    # Uploaded avatars get a new storage URL when replaced, so their existing
    # URLs are safe to keep in the browser cache.
    return serve(request, path, document_root=settings.MEDIA_ROOT)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("receipts.urls")),
    re_path(r"^media/(?P<path>.*)$", serve_media),
]
