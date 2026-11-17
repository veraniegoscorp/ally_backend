from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q


class StudyCategory(models.Model):
    class Technique(models.TextChoices):
        POMODORO = "pomodoro", "Pomodoro"
        CONTINUOUS = "continuous", "Bloques continuos"
        MILESTONES = "milestones", "Avances por hitos"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="study_categories",
    )
    name = models.CharField(max_length=80)
    technique = models.CharField(
        max_length=16,
        choices=Technique.choices,
        default=Technique.POMODORO,
    )
    session_minutes = models.PositiveSmallIntegerField(default=50)
    minimum_session_minutes = models.PositiveSmallIntegerField(default=25)
    break_minutes = models.PositiveSmallIntegerField(default=5)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=("user", "name"),
                name="unique_study_category_name_per_user",
            ),
            models.CheckConstraint(
                condition=Q(session_minutes__gt=0),
                name="study_category_session_minutes_positive",
            ),
            models.CheckConstraint(
                condition=Q(minimum_session_minutes__gt=0)
                & Q(minimum_session_minutes__lte=F("session_minutes")),
                name="study_category_min_session_valid",
            ),
        ]

    def __str__(self):
        return self.name


class AvailabilityWindow(models.Model):
    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Lunes"
        TUESDAY = 1, "Martes"
        WEDNESDAY = 2, "Miércoles"
        THURSDAY = 3, "Jueves"
        FRIDAY = 4, "Viernes"
        SATURDAY = 5, "Sábado"
        SUNDAY = 6, "Domingo"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="availability_windows",
    )
    title = models.CharField(max_length=100)
    weekday = models.PositiveSmallIntegerField(
        choices=Weekday.choices,
        null=True,
        blank=True,
    )
    specific_date = models.DateField(null=True, blank=True)
    starts_at = models.TimeField()
    ends_at = models.TimeField()
    is_available = models.BooleanField(
        default=False,
        help_text="True indica horas disponibles; False bloquea esas horas.",
    )

    class Meta:
        ordering = ("specific_date", "weekday", "starts_at")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(weekday__isnull=False, specific_date__isnull=True)
                    | Q(weekday__isnull=True, specific_date__isnull=False)
                ),
                name="availability_window_has_one_recurrence",
            ),
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")),
                name="availability_window_end_after_start",
            ),
            models.CheckConstraint(
                condition=Q(weekday__isnull=True) | Q(weekday__lte=6),
                name="availability_window_weekday_valid",
            ),
        ]

    def clean(self):
        super().clean()
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "La hora de fin debe ser posterior al inicio."})

    def __str__(self):
        return self.title


class GoalEvent(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Activa"
        COMPLETED = "completed", "Completada"
        CANCELLED = "cancelled", "Cancelada"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="goal_events",
    )
    category = models.ForeignKey(
        StudyCategory,
        on_delete=models.PROTECT,
        related_name="goals",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    deadline = models.DateTimeField()
    minimum_study_minutes = models.PositiveIntegerField()
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("deadline",)
        constraints = [
            models.CheckConstraint(
                condition=Q(minimum_study_minutes__gt=0),
                name="goal_minimum_study_minutes_positive",
            ),
        ]

    def clean(self):
        super().clean()
        if self.category_id and self.user_id:
            if self.category.user_id != self.user_id:
                raise ValidationError({"category": "La categoría debe pertenecer al mismo usuario."})

    def __str__(self):
        return self.title


class Subtask(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="study_subtasks",
    )
    goal = models.ForeignKey(
        GoalEvent,
        on_delete=models.CASCADE,
        related_name="subtasks",
    )
    title = models.CharField(max_length=200)
    position = models.PositiveIntegerField(default=0)
    is_completed = models.BooleanField(default=False)

    class Meta:
        ordering = ("position", "id")

    def clean(self):
        super().clean()
        if self.goal_id and self.user_id and self.goal.user_id != self.user_id:
            raise ValidationError({"goal": "La meta debe pertenecer al mismo usuario."})

    def __str__(self):
        return self.title


class StudyBlock(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Programado"
        COMPLETED = "completed", "Completado"
        CANCELLED = "cancelled", "Cancelado"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="study_blocks",
    )
    goal = models.ForeignKey(
        GoalEvent,
        on_delete=models.CASCADE,
        related_name="study_blocks",
    )
    subtask = models.ForeignKey(
        Subtask,
        on_delete=models.SET_NULL,
        related_name="study_blocks",
        null=True,
        blank=True,
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.SCHEDULED,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("starts_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")),
                name="study_block_end_after_start",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            errors["ends_at"] = "La hora de fin debe ser posterior al inicio."
        if self.goal_id and self.user_id and self.goal.user_id != self.user_id:
            errors["goal"] = "La meta debe pertenecer al mismo usuario."
        if self.subtask_id and self.goal_id:
            if self.subtask.goal_id != self.goal_id:
                errors["subtask"] = "La subtarea debe pertenecer a la meta del bloque."
            elif self.subtask.user_id != self.user_id:
                errors["subtask"] = "La subtarea debe pertenecer al mismo usuario."
        if errors:
            raise ValidationError(errors)

    @property
    def duration_minutes(self):
        return int((self.ends_at - self.starts_at).total_seconds() // 60)

    def __str__(self):
        return f"{self.goal.title} ({self.starts_at:%Y-%m-%d %H:%M})"
