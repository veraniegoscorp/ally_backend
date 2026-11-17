from datetime import datetime, time, timedelta, timezone

from django.test import SimpleTestCase

from .scheduler import (
    AvailabilityRule,
    InsufficientAvailabilityError,
    TimeSlot,
    calculate_plan_from_rules,
    calculate_study_plan,
)


class SchedulerTests(SimpleTestCase):
    def test_subtracts_blocked_time_and_spreads_sessions_across_days(self):
        day_one = datetime(2026, 11, 17, tzinfo=timezone.utc)
        day_two = day_one + timedelta(days=1)
        available = [
            TimeSlot(day_one.replace(hour=9), day_one.replace(hour=12)),
            TimeSlot(day_two.replace(hour=9), day_two.replace(hour=12)),
        ]
        blocked = [TimeSlot(day_one.replace(hour=10), day_one.replace(hour=11))]

        plan = calculate_study_plan(
            available,
            blocked,
            day_one,
            day_two.replace(hour=12),
            required_minutes=120,
            max_session_minutes=60,
            min_session_minutes=30,
        )

        self.assertEqual(sum(slot.minutes for slot in plan), 120)
        self.assertEqual({slot.start.date() for slot in plan}, {day_one.date(), day_two.date()})
        self.assertFalse(any(slot.start < blocked[0].end and slot.end > blocked[0].start for slot in plan))

    def test_raises_when_free_time_is_insufficient(self):
        start = datetime(2026, 11, 17, 9, tzinfo=timezone.utc)
        with self.assertRaises(InsufficientAvailabilityError):
            calculate_study_plan(
                [TimeSlot(start, start + timedelta(minutes=30))],
                [],
                start,
                start + timedelta(hours=1),
                required_minutes=60,
            )

    def test_distributes_non_even_session_lengths_without_losing_minutes(self):
        start = datetime(2026, 11, 17, 9, tzinfo=timezone.utc)
        plan = calculate_study_plan(
            [TimeSlot(start, start + timedelta(minutes=181))],
            [],
            start,
            start + timedelta(hours=4),
            required_minutes=181,
            max_session_minutes=50,
            min_session_minutes=25,
        )

        self.assertEqual(sum(slot.minutes for slot in plan), 181)

    def test_merges_overlapping_availability_without_double_booking(self):
        start = datetime(2026, 11, 17, 9, tzinfo=timezone.utc)
        plan = calculate_study_plan(
            [
                TimeSlot(start, start + timedelta(hours=2)),
                TimeSlot(start + timedelta(hours=1), start + timedelta(hours=3)),
            ],
            [],
            start,
            start + timedelta(hours=3),
            required_minutes=180,
            max_session_minutes=60,
            min_session_minutes=30,
        )

        self.assertEqual(sum(slot.minutes for slot in plan), 180)
        self.assertEqual(len(plan), 3)
        self.assertTrue(all(left.end <= right.start for left, right in zip(plan, plan[1:])))

    def test_preserves_minimum_session_length_for_small_remainder(self):
        start = datetime(2026, 11, 17, 9, tzinfo=timezone.utc)
        plan = calculate_study_plan(
            [TimeSlot(start, start + timedelta(minutes=100))],
            [],
            start,
            start + timedelta(hours=2),
            required_minutes=55,
            max_session_minutes=50,
            min_session_minutes=25,
        )

        self.assertEqual([slot.minutes for slot in plan], [30, 25])

    def test_expands_weekly_availability_and_applies_dated_block(self):
        start = datetime(2026, 11, 17, tzinfo=timezone.utc)
        rules = [
            AvailabilityRule(time(9), time(12), True, weekday=1),
            AvailabilityRule(
                time(10),
                time(11),
                False,
                specific_date=start.date(),
            ),
        ]

        plan = calculate_plan_from_rules(
            rules,
            [],
            start,
            start + timedelta(days=7),
            required_minutes=120,
            max_session_minutes=60,
            min_session_minutes=30,
        )

        self.assertEqual(sum(slot.minutes for slot in plan), 120)
        self.assertTrue(all(slot.start.hour != 10 or slot.start.date() != start.date() for slot in plan))
