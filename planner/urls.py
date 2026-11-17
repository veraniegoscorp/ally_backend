from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AvailabilityWindowViewSet,
    GoalEventViewSet,
    RegisterView,
    StudyBlockViewSet,
    StudyCategoryViewSet,
    SubtaskViewSet,
)

router = DefaultRouter()
router.register("categories", StudyCategoryViewSet, basename="category")
router.register("availability", AvailabilityWindowViewSet, basename="availability")
router.register("goals", GoalEventViewSet, basename="goal")
router.register("subtasks", SubtaskViewSet, basename="subtask")
router.register("blocks", StudyBlockViewSet, basename="block")

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("", include(router.urls)),
]
