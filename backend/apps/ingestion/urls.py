from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r"ingestions", views.DataIngestionViewSet, basename="ingestion")

urlpatterns = [
    path("", include(router.urls)),
]
