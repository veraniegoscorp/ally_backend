from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import AvailabilityWindow, GoalEvent, StudyBlock, StudyCategory, Subtask
from .serializers import (
    AvailabilityWindowSerializer,
    GoalEventSerializer,
    RegisterSerializer,
    StudyBlockSerializer,
    StudyCategorySerializer,
    SubtaskSerializer,
)
from .services import schedule_goal


class RegisterView(generics.CreateAPIView):
    queryset = get_user_model().objects.all()
    serializer_class = RegisterSerializer
    permission_classes = (permissions.AllowAny,)


class UserScopedViewSet(viewsets.ModelViewSet):
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class StudyCategoryViewSet(UserScopedViewSet):
    serializer_class = StudyCategorySerializer

    def get_queryset(self):
        return StudyCategory.objects.filter(user=self.request.user)


class AvailabilityWindowViewSet(UserScopedViewSet):
    serializer_class = AvailabilityWindowSerializer

    def get_queryset(self):
        return AvailabilityWindow.objects.filter(user=self.request.user)


class GoalEventViewSet(UserScopedViewSet):
    serializer_class = GoalEventSerializer

    def get_queryset(self):
        return GoalEvent.objects.filter(user=self.request.user).select_related("category")

    @action(detail=True, methods=("post",))
    def schedule(self, request, pk=None):
        goal = self.get_object()
        blocks = schedule_goal(goal)
        return Response(
            StudyBlockSerializer(blocks, many=True, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


class SubtaskViewSet(UserScopedViewSet):
    serializer_class = SubtaskSerializer

    def get_queryset(self):
        return Subtask.objects.filter(user=self.request.user).select_related("goal")


class StudyBlockViewSet(UserScopedViewSet):
    serializer_class = StudyBlockSerializer

    def get_queryset(self):
        return StudyBlock.objects.filter(user=self.request.user).select_related(
            "goal",
            "subtask",
        )

    def perform_update(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        with transaction.atomic():
            if instance.status == StudyBlock.Status.SCHEDULED:
                instance.status = StudyBlock.Status.CANCELLED
                instance.save(update_fields=("status",))
            else:
                instance.delete()
