#!/usr/bin/env python3
"""
Example objective classes for schedule optimization.

These demonstrate common scheduling objectives that can be combined
in different orders to create customized optimization strategies.
"""

from .objective_base import ObjectiveBase
from pulp import lpSum
from .scheduler import filter_keys
from .utils import time_to_minutes
from typing import Optional, List


class MinimizeClassesBefore(ObjectiveBase):
    """
    Minimize classes scheduled before a given time.

    Useful for avoiding early morning classes or accommodating
    instructor preferences.
    """

    def __init__(
        self,
        time: str,
        instructor: Optional[str] = None,
        sense: str = 'minimize',
        tolerance: float = 0.0
    ):
        """
        Args:
            time: Time in HH:MM format (e.g., "9:00")
            instructor: If specified, only count this instructor's classes
            sense: 'minimize' or 'maximize'
            tolerance: Fractional tolerance for lexicographic constraint
        """
        self.time = time
        self.time_minutes = time_to_minutes(time)
        self.instructor = instructor

        name_parts = [f"classes before {time}"]
        if instructor:
            name_parts.append(f"for {instructor}")

        super().__init__(
            name=f"{sense.capitalize()} {' '.join(name_parts)}",
            sense=sense,
            tolerance=tolerance
        )

    def evaluate(self, scheduler):
        def matches_criteria(course, room, time_slot):
            # Check time constraint
            slot_start = scheduler.slot_start_minutes[time_slot]
            if slot_start >= self.time_minutes:
                return False

            # Check instructor constraint
            if self.instructor:
                course_instructor = scheduler.courses_df[
                    scheduler.courses_df['Course'] == course
                ]['Instructor'].values[0]
                if course_instructor != self.instructor:
                    return False

            return True

        filtered = filter_keys(scheduler.keys, predicate=matches_criteria)
        return lpSum(scheduler.x[k] for k in filtered)


class MinimizeClassesAfter(ObjectiveBase):
    """
    Minimize classes scheduled after a given time.

    Useful for avoiding late afternoon/evening classes.
    """

    def __init__(
        self,
        time: str,
        instructor: Optional[str] = None,
        course_type: Optional[str] = None,
        sense: str = 'minimize',
        tolerance: float = 0.0
    ):
        """
        Args:
            time: Time in HH:MM format (e.g., "16:00")
            instructor: If specified, only count this instructor's classes
            course_type: If specified, only count this type ('Lecture' or 'Lab')
            sense: 'minimize' or 'maximize'
            tolerance: Fractional tolerance for lexicographic constraint
        """
        self.time = time
        self.time_minutes = time_to_minutes(time)
        self.instructor = instructor
        self.course_type = course_type

        name_parts = [f"classes after {time}"]
        if instructor:
            name_parts.append(f"for {instructor}")
        if course_type:
            name_parts.append(f"({course_type})")

        super().__init__(
            name=f"{sense.capitalize()} {' '.join(name_parts)}",
            sense=sense,
            tolerance=tolerance
        )

    def evaluate(self, scheduler):
        def matches_criteria(course, room, time_slot):
            # Check time constraint
            slot_start = scheduler.slot_start_minutes[time_slot]
            if slot_start <= self.time_minutes:
                return False

            # Check instructor constraint
            if self.instructor:
                course_instructor = scheduler.courses_df[
                    scheduler.courses_df['Course'] == course
                ]['Instructor'].values[0]
                if course_instructor != self.instructor:
                    return False

            # Check course type constraint
            if self.course_type:
                if scheduler.course_types[course] != self.course_type:
                    return False

            return True

        filtered = filter_keys(scheduler.keys, predicate=matches_criteria)
        return lpSum(scheduler.x[k] for k in filtered)


class MaximizePreferredRooms(ObjectiveBase):
    """
    Maximize use of preferred rooms.

    Useful for assigning courses to rooms with specific equipment,
    better location, or instructor preferences.
    """

    def __init__(
        self,
        preferred_rooms: List[str],
        instructor: Optional[str] = None,
        course_type: Optional[str] = None,
        tolerance: float = 0.0
    ):
        """
        Args:
            preferred_rooms: List of room names to prefer
            instructor: If specified, only for this instructor's classes
            course_type: If specified, only for this type ('Lecture' or 'Lab')
            tolerance: Fractional tolerance for lexicographic constraint
        """
        self.preferred_rooms = set(preferred_rooms)
        self.instructor = instructor
        self.course_type = course_type

        name_parts = [f"preferred rooms ({', '.join(preferred_rooms)})"]
        if instructor:
            name_parts.append(f"for {instructor}")
        if course_type:
            name_parts.append(f"({course_type})")

        super().__init__(
            name=f"Maximize {' '.join(name_parts)}",
            sense='maximize',
            tolerance=tolerance
        )

    def evaluate(self, scheduler):
        def matches_criteria(course, room, time_slot):
            # Check room constraint
            if room not in self.preferred_rooms:
                return False

            # Check instructor constraint
            if self.instructor:
                course_instructor = scheduler.courses_df[
                    scheduler.courses_df['Course'] == course
                ]['Instructor'].values[0]
                if course_instructor != self.instructor:
                    return False

            # Check course type constraint
            if self.course_type:
                if scheduler.course_types[course] != self.course_type:
                    return False

            return True

        filtered = filter_keys(scheduler.keys, predicate=matches_criteria)
        return lpSum(scheduler.x[k] for k in filtered)
