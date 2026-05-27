from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r"activity-records", views.ActivityRecordViewSet, basename="activity-record")

urlpatterns = [
    path("", include(router.urls)),
]
