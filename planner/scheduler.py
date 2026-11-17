"""Pure-Python scheduling helpers; recurrence rules are expanded by the caller."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from math import ceil
from typing import Iterable


class InsufficientAvailabilityError(ValueError):
    """Raised when the available time cannot meet the requested study duration."""


@dataclass(frozen=True, order=True)
class TimeSlot:
    start: datetime
    end: datetime

    def __post_init__(self):
        if self.end <= self.start:
            raise ValueError("A time slot must end after it starts.")

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


@dataclass(frozen=True)
class AvailabilityRule:
    starts_at: time
    ends_at: time
    is_available: bool
    weekday: int | None = None
    specific_date: date | None = None

    def __post_init__(self):
        if (self.weekday is None) == (self.specific_date is None):
            raise ValueError("Set exactly one of weekday or specific_date.")
        if self.weekday is not None and not 0 <= self.weekday <= 6:
            raise ValueError("weekday must be between 0 (Monday) and 6 (Sunday).")
        if self.ends_at <= self.starts_at:
            raise ValueError("An availability rule must end after it starts.")


def expand_availability_rules(
    rules: Iterable[AvailabilityRule],
    start_at: datetime,
    deadline: datetime,
) -> tuple[list[TimeSlot], list[TimeSlot]]:
    """Expand weekly and dated rules into concrete windows in start_at's timezone."""
    if deadline <= start_at:
        raise ValueError("The deadline must be later than the planning start.")

    available, blocked = [], []
    current_date = start_at.date()
    while current_date <= deadline.date():
        for rule in rules:
            matches = (
                rule.specific_date == current_date
                if rule.specific_date is not None
                else rule.weekday == current_date.weekday()
            )
            if not matches:
                continue
            start = datetime.combine(current_date, rule.starts_at, tzinfo=start_at.tzinfo)
            end = datetime.combine(current_date, rule.ends_at, tzinfo=start_at.tzinfo)
            (available if rule.is_available else blocked).append(TimeSlot(start, end))
        current_date += timedelta(days=1)
    return available, blocked


def find_free_slots(
    available_windows: Iterable[TimeSlot],
    blocked_windows: Iterable[TimeSlot],
    start_at: datetime,
    deadline: datetime,
) -> list[TimeSlot]:
    """Clip availability to the planning range and subtract busy/blocked intervals."""
    if deadline <= start_at:
        raise ValueError("The deadline must be later than the planning start.")

    blocks = sorted(
        TimeSlot(max(block.start, start_at), min(block.end, deadline))
        for block in blocked_windows
        if block.start < deadline and block.end > start_at
    )
    merged_windows = []
    for window in sorted(available_windows):
        start = max(window.start, start_at)
        end = min(window.end, deadline)
        if start >= end:
            continue
        if merged_windows and start <= merged_windows[-1].end:
            previous = merged_windows[-1]
            merged_windows[-1] = TimeSlot(previous.start, max(previous.end, end))
        else:
            merged_windows.append(TimeSlot(start, end))

    free_slots = []
    for window in merged_windows:
        start, end = window.start, window.end
        free_ranges = [(start, end)]
        for block in blocks:
            if block.end <= start or block.start >= end:
                continue
            remaining = []
            for free_start, free_end in free_ranges:
                if block.end <= free_start or block.start >= free_end:
                    remaining.append((free_start, free_end))
                    continue
                if free_start < block.start:
                    remaining.append((free_start, block.start))
                if block.end < free_end:
                    remaining.append((block.end, free_end))
            free_ranges = remaining
            if not free_ranges:
                break

        free_slots.extend(TimeSlot(free_start, free_end) for free_start, free_end in free_ranges)
    return sorted(free_slots)


def _session_slots(
    free_slots: Iterable[TimeSlot],
    max_session_minutes: int,
    min_session_minutes: int,
) -> list[TimeSlot]:
    candidates = []
    for slot in free_slots:
        total_minutes = slot.minutes
        if total_minutes < min_session_minutes:
            continue
        session_count = ceil(total_minutes / max_session_minutes)
        while session_count > 1 and total_minutes / session_count < min_session_minutes:
            session_count -= 1

        cursor = slot.start
        base_duration, extra_minutes = divmod(total_minutes, session_count)
        for index in range(session_count):
            duration = base_duration + (index < extra_minutes)
            session_end = cursor + timedelta(minutes=duration)
            candidates.append(TimeSlot(cursor, session_end))
            cursor = session_end
    return candidates


def distribute_study_minutes(
    free_slots: Iterable[TimeSlot],
    required_minutes: int,
    max_session_minutes: int = 50,
    min_session_minutes: int = 25,
) -> list[TimeSlot]:
    """Allocate sessions across dates in rounds, balancing work over available days."""
    if required_minutes <= 0:
        raise ValueError("required_minutes must be positive.")
    if min_session_minutes <= 0 or max_session_minutes < min_session_minutes:
        raise ValueError("Session limits must satisfy 0 < minimum <= maximum.")

    by_day = defaultdict(list)
    for slot in _session_slots(free_slots, max_session_minutes, min_session_minutes):
        by_day[slot.start.date()].append(slot)
    days = sorted(by_day)
    candidates = [
        by_day[day][index]
        for index in range(max((len(slots) for slots in by_day.values()), default=0))
        for day in days
        if index < len(by_day[day])
    ]
    if not candidates:
        raise InsufficientAvailabilityError("No hay franjas libres suficientes para agendar.")

    session_count = next(
        (
            count
            for count in range(1, len(candidates) + 1)
            if count * min_session_minutes <= required_minutes
            and sum(slot.minutes for slot in candidates[:count]) >= required_minutes
        ),
        None,
    )
    if session_count is None:
        raise InsufficientAvailabilityError(
            "Las franjas disponibles no alcanzan para cubrir las horas mínimas."
        )

    plan = []
    remaining = required_minutes
    for index, candidate in enumerate(candidates[:session_count]):
        sessions_left = session_count - index - 1
        duration = min(
            candidate.minutes,
            remaining - sessions_left * min_session_minutes,
        )
        if duration < min_session_minutes:
            raise InsufficientAvailabilityError(
                "Las franjas disponibles no alcanzan para cubrir las horas mínimas."
            )
        plan.append(TimeSlot(candidate.start, candidate.start + timedelta(minutes=duration)))
        remaining -= duration
    return sorted(plan)


def calculate_study_plan(
    available_windows: Iterable[TimeSlot],
    blocked_windows: Iterable[TimeSlot],
    start_at: datetime,
    deadline: datetime,
    required_minutes: int,
    max_session_minutes: int = 50,
    min_session_minutes: int = 25,
) -> list[TimeSlot]:
    free_slots = find_free_slots(
        available_windows,
        blocked_windows,
        start_at,
        deadline,
    )
    return distribute_study_minutes(
        free_slots,
        required_minutes,
        max_session_minutes,
        min_session_minutes,
    )


def calculate_plan_from_rules(
    rules: Iterable[AvailabilityRule],
    busy_windows: Iterable[TimeSlot],
    start_at: datetime,
    deadline: datetime,
    required_minutes: int,
    max_session_minutes: int = 50,
    min_session_minutes: int = 25,
) -> list[TimeSlot]:
    available, blocked = expand_availability_rules(rules, start_at, deadline)
    return calculate_study_plan(
        available,
        [*blocked, *busy_windows],
        start_at,
        deadline,
        required_minutes,
        max_session_minutes,
        min_session_minutes,
    )
