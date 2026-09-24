"""Test URL config — mounts aa_eveaio under /eveaio/ exactly like
Alliance Auth's UrlHook does in production."""

from django.urls import include, path

urlpatterns = [
    path("eveaio/", include("aa_eveaio.urls")),
]
