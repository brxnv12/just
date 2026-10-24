from django.contrib import admin
from django.urls import include, path, re_path

from gas_app.payme import payme_endpoint
from gas_app.views import IndexView, media_view

admin.site.site_header = "Hududgaz boshqaruv paneli"
admin.site.site_title = "Hududgaz"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/payme/", payme_endpoint),
    path("api/", include("gas_app.urls")),
    re_path(r"^media/(?P<path>.*)$", media_view),
    path("", IndexView.as_view(), name="index"),
]
