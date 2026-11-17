from django.contrib import admin

from .models import AvailabilityWindow, GoalEvent, StudyBlock, StudyCategory, Subtask


@admin.register(StudyCategory)
class StudyCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "technique", "session_minutes", "break_minutes")
    list_filter = ("technique",)
    search_fields = ("name", "user__username", "user__email")
    list_select_related = ("user",)


@admin.register(AvailabilityWindow)
class AvailabilityWindowAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "user",
        "weekday",
        "specific_date",
        "starts_at",
        "ends_at",
        "is_available",
    )
    list_filter = ("is_available", "weekday", "specific_date")
    search_fields = ("title", "user__username", "user__email")
    list_select_related = ("user",)
    date_hierarchy = "specific_date"


@admin.register(GoalEvent)
class GoalEventAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "category", "deadline", "minimum_study_minutes", "status")
    list_filter = ("status", "category__technique")
    search_fields = ("title", "user__username", "user__email", "category__name")
    list_select_related = ("user", "category")
    date_hierarchy = "deadline"
    readonly_fields = ("created_at", "updated_at")


@admin.register(Subtask)
class SubtaskAdmin(admin.ModelAdmin):
    list_display = ("title", "goal", "user", "position", "is_completed")
    list_filter = ("is_completed",)
    search_fields = ("title", "goal__title", "user__username", "user__email")
    list_select_related = ("goal", "user")


@admin.register(StudyBlock)
class StudyBlockAdmin(admin.ModelAdmin):
    list_display = ("goal", "user", "starts_at", "ends_at", "duration_minutes", "status")
    list_filter = ("status",)
    search_fields = ("goal__title", "user__username", "user__email")
    list_select_related = ("goal", "user", "subtask")
    date_hierarchy = "starts_at"
    readonly_fields = ("created_at", "duration_minutes")
