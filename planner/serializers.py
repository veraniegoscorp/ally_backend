from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import serializers

from .models import AvailabilityWindow, GoalEvent, StudyBlock, StudyCategory, Subtask

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ("id", "username", "email", "password")
        read_only_fields = ("id",)

    def validate_password(self, value):
        try:
            password_validation.validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class StudyCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = StudyCategory
        fields = (
            "id",
            "name",
            "technique",
            "session_minutes",
            "minimum_session_minutes",
            "break_minutes",
        )
        read_only_fields = ("id",)

    def validate_name(self, value):
        categories = StudyCategory.objects.filter(
            user=self.context["request"].user,
            name=value,
        )
        if self.instance:
            categories = categories.exclude(pk=self.instance.pk)
        if categories.exists():
            raise serializers.ValidationError("Ya tienes una categoría con este nombre.")
        return value


class AvailabilityWindowSerializer(serializers.ModelSerializer):
    class Meta:
        model = AvailabilityWindow
        fields = (
            "id",
            "title",
            "weekday",
            "specific_date",
            "starts_at",
            "ends_at",
            "is_available",
        )
        read_only_fields = ("id",)

    def validate(self, attrs):
        weekday = attrs.get("weekday", getattr(self.instance, "weekday", None))
        specific_date = attrs.get(
            "specific_date",
            getattr(self.instance, "specific_date", None),
        )
        starts_at = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        ends_at = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if (weekday is None) == (specific_date is None):
            raise serializers.ValidationError(
                "Indica exactamente uno: weekday para recurrencia o specific_date para una fecha puntual."
            )
        if starts_at and ends_at and ends_at <= starts_at:
            raise serializers.ValidationError(
                {"ends_at": "La hora de fin debe ser posterior al inicio."}
            )
        return attrs


class GoalEventSerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(
        queryset=StudyCategory.objects.none(),
    )

    class Meta:
        model = GoalEvent
        fields = (
            "id",
            "category",
            "title",
            "description",
            "deadline",
            "minimum_study_minutes",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "request" in self.context:
            self.fields["category"].queryset = StudyCategory.objects.filter(
                user=self.context["request"].user
            )


class SubtaskSerializer(serializers.ModelSerializer):
    goal = serializers.PrimaryKeyRelatedField(queryset=GoalEvent.objects.none())

    class Meta:
        model = Subtask
        fields = ("id", "goal", "title", "position", "is_completed")
        read_only_fields = ("id",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "request" in self.context:
            self.fields["goal"].queryset = GoalEvent.objects.filter(
                user=self.context["request"].user
            )


class StudyBlockSerializer(serializers.ModelSerializer):
    goal = serializers.PrimaryKeyRelatedField(queryset=GoalEvent.objects.none())
    subtask = serializers.PrimaryKeyRelatedField(
        queryset=Subtask.objects.none(),
        required=False,
        allow_null=True,
    )
    duration_minutes = serializers.IntegerField(read_only=True)

    class Meta:
        model = StudyBlock
        fields = (
            "id",
            "goal",
            "subtask",
            "starts_at",
            "ends_at",
            "status",
            "duration_minutes",
        )
        read_only_fields = ("id",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "request" in self.context:
            user = self.context["request"].user
            self.fields["goal"].queryset = GoalEvent.objects.filter(user=user)
            self.fields["subtask"].queryset = Subtask.objects.filter(user=user)

    def validate(self, attrs):
        goal = attrs.get("goal", getattr(self.instance, "goal", None))
        subtask = attrs.get("subtask", getattr(self.instance, "subtask", None))
        starts_at = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        ends_at = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if subtask and goal and subtask.goal_id != goal.id:
            raise serializers.ValidationError(
                {"subtask": "La subtarea debe pertenecer a la meta del bloque."}
            )
        if starts_at and ends_at and ends_at <= starts_at:
            raise serializers.ValidationError(
                {"ends_at": "La hora de fin debe ser posterior al inicio."}
            )
        status_value = attrs.get("status", getattr(self.instance, "status", StudyBlock.Status.SCHEDULED))
        if starts_at and ends_at and status_value == StudyBlock.Status.SCHEDULED:
            from .services import validate_block_slot

            validate_block_slot(
                user=self.context["request"].user,
                starts_at=starts_at,
                ends_at=ends_at,
                exclude_block=self.instance,
            )
        return attrs
