from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import AvailabilityWindow, GoalEvent, StudyBlock
from .scheduler import (
    AvailabilityRule,
    InsufficientAvailabilityError,
    TimeSlot,
    calculate_plan_from_rules,
    expand_availability_rules,
    find_free_slots,
)


def _availability_rules(user, start_at, deadline):
    dates = []
    current_date = start_at.date()
    while current_date <= deadline.date():
        dates.append(current_date)
        current_date += timedelta(days=1)

    windows = AvailabilityWindow.objects.filter(user=user).filter(
        Q(specific_date__in=dates) | Q(weekday__in={day.weekday() for day in dates})
    )
    return [
        AvailabilityRule(
            starts_at=window.starts_at,
            ends_at=window.ends_at,
            is_available=window.is_available,
            weekday=window.weekday,
            specific_date=window.specific_date,
        )
        for window in windows
    ]


def _busy_slots(user, start_at, deadline, exclude_block=None, exclude_goal=None):
    blocks = StudyBlock.objects.filter(
        user=user,
        status=StudyBlock.Status.SCHEDULED,
        starts_at__lt=deadline,
        ends_at__gt=start_at,
    )
    if exclude_block:
        blocks = blocks.exclude(pk=exclude_block.pk)
    if exclude_goal:
        blocks = blocks.exclude(goal=exclude_goal)
    return [TimeSlot(block.starts_at, block.ends_at) for block in blocks]


def validate_block_slot(user, starts_at, ends_at, exclude_block=None):
    local_start = timezone.localtime(starts_at, timezone.get_current_timezone())
    local_end = timezone.localtime(ends_at, timezone.get_current_timezone())
    rules = _availability_rules(user, local_start, local_end)
    available, blocked = expand_availability_rules(rules, local_start, local_end)
    free = find_free_slots(
        available,
        [
            *blocked,
            *_busy_slots(user, starts_at, ends_at, exclude_block=exclude_block),
        ],
        local_start,
        local_end,
    )
    if not any(slot.start <= local_start and slot.end >= local_end for slot in free):
        raise ValidationError(
            "El horario del bloque no está disponible o se superpone con otro bloque."
        )


@transaction.atomic
def schedule_goal(goal: GoalEvent):
    now = timezone.localtime(timezone.now(), timezone.get_current_timezone())
    deadline = timezone.localtime(goal.deadline, timezone.get_current_timezone())
    if deadline <= now:
        raise ValidationError({"deadline": "La fecha límite debe estar en el futuro."})

    rules = _availability_rules(goal.user, now, deadline)
    busy_slots = _busy_slots(
        goal.user,
        now,
        deadline,
        exclude_goal=goal,
    )
    try:
        plan = calculate_plan_from_rules(
            rules,
            busy_slots,
            now,
            deadline,
            goal.minimum_study_minutes,
            max_session_minutes=goal.category.session_minutes,
            min_session_minutes=goal.category.minimum_session_minutes,
        )
    except InsufficientAvailabilityError as exc:
        raise ValidationError({"schedule": str(exc)}) from exc
    except ValueError as exc:
        raise ValidationError({"schedule": str(exc)}) from exc

    StudyBlock.objects.filter(
        goal=goal,
        status=StudyBlock.Status.SCHEDULED,
        starts_at__gte=now,
    ).delete()
    return StudyBlock.objects.bulk_create(
        [
            StudyBlock(
                user=goal.user,
                goal=goal,
                starts_at=slot.start,
                ends_at=slot.end,
            )
            for slot in plan
        ]
    )
