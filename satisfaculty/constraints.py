#!/usr/bin/env python3
"""
Core constraint classes for schedule optimization.

These define the feasibility requirements that all valid schedules must satisfy.
"""

import pandas as pd
from .constraint_base import ConstraintBase
from pulp import lpSum
from .scheduler import filter_keys


class AssignAllCourses(ConstraintBase):
    """Ensures each course is scheduled exactly once."""

    def __init__(self):
        super().__init__(name="Assign all courses")

    def apply(self, scheduler) -> int:
        count = 0
        for course in scheduler.courses:
            scheduler.prob += (
                lpSum(scheduler.x[k] for k in filter_keys(scheduler.keys, course=course)) == 1,
                f"assign_course_{course}"
            )
            count += 1
        return count


class NoInstructorOverlap(ConstraintBase):
    """Ensures an instructor can only teach one course at a time."""

    def __init__(self):
        super().__init__(name="No instructor overlap")

    def apply(self, scheduler) -> int:
        day_start_pairs = scheduler.get_day_start_pairs()

        count = 0
        for instructor in scheduler.instructors:
            for day, start_minutes in day_start_pairs:
                overlapping_keys = [
                    k for k in scheduler.keys
                    if scheduler.a[(instructor, k[0])] == 1
                    and scheduler.slot_overlaps(k[2], day, start_minutes)
                ]

                if overlapping_keys:
                    scheduler.prob += (
                        lpSum(scheduler.x[k] for k in overlapping_keys) <= 1,
                        f"no_instructor_overlap_{instructor}_{day}_{start_minutes}"
                    )
                    count += 1
        return count


class NoRoomOverlap(ConstraintBase):
    """Ensures a room can only host one course at a time."""

    def __init__(self):
        super().__init__(name="No room overlap")

    def apply(self, scheduler) -> int:
        day_start_pairs = scheduler.get_day_start_pairs()

        count = 0
        for room in scheduler.rooms:
            for day, start_minutes in day_start_pairs:
                overlapping_keys = [
                    k for k in scheduler.keys
                    if k[1] == room
                    and scheduler.slot_overlaps(k[2], day, start_minutes)
                ]

                if overlapping_keys:
                    scheduler.prob += (
                        lpSum(scheduler.x[k] for k in overlapping_keys) <= 1,
                        f"no_room_overlap_{room}_{day}_{start_minutes}"
                    )
                    count += 1
        return count


class RoomCapacity(ConstraintBase):
    """Ensures room capacity is not exceeded by course enrollment."""

    def __init__(self):
        super().__init__(name="Room capacity")

    def apply(self, scheduler) -> int:
        count = 0
        for k in scheduler.keys:
            course, room, _ = k
            if scheduler.enrollments[course] > scheduler.capacities[room]:
                scheduler.x[k].upBound = 0
                count += 1
        return count


class AvoidRoomsForCourseType(ConstraintBase):
    """Disallow specific rooms for a given course type."""

    def __init__(self, rooms: list[str], course_type: str):
        self.rooms = set(rooms)
        self.course_type = course_type
        super().__init__(name=f"Avoid rooms ({', '.join(rooms)}) for {course_type}")

    def apply(self, scheduler) -> int:
        count = 0
        for course, room, time_slot in scheduler.keys:
            if scheduler.course_slot_type[course] == self.course_type and room in self.rooms:
                scheduler.x[(course, room, time_slot)].upBound = 0
                count += 1
        return count


class ForceRooms(ConstraintBase):
    """Forces specific courses to be assigned to specific rooms."""

    def __init__(self, column: str = 'Force Room'):
        self.column = column
        super().__init__(name=f"Force rooms ({column})")

    def apply(self, scheduler) -> int:
        df = scheduler.courses_df
        if self.column not in df.columns:
            return 0
        count = 0
        for _, row in df.iterrows():
            course = row['Course']
            forced_room = row[self.column]
            if pd.notna(forced_room) and str(forced_room).strip() != '':
                forced_room = str(forced_room).strip()
                scheduler.prob += (
                    lpSum(scheduler.x[k] for k in filter_keys(scheduler.keys, course=course, room=forced_room)) == 1,
                    f"force_room_{course}"
                )
                count += 1
        return count


class ForceTimeSlots(ConstraintBase):
    """Forces specific courses to be assigned to specific time slots."""

    def __init__(self, column: str = 'Force Time Slot'):
        self.column = column
        super().__init__(name=f"Force time slots ({column})")

    def apply(self, scheduler) -> int:
        df = scheduler.courses_df
        if self.column not in df.columns:
            return 0
        count = 0
        for _, row in df.iterrows():
            course = row['Course']
            forced_slot = row[self.column]
            if pd.notna(forced_slot) and str(forced_slot).strip() != '':
                forced_slot = str(forced_slot).strip()
                scheduler.prob += (
                    lpSum(scheduler.x[k] for k in filter_keys(scheduler.keys, course=course, time_slot=forced_slot)) == 1,
                    f"force_time_slot_{course}"
                )
                count += 1
        return count


class NoCourseOverlap(ConstraintBase):
    """Prevents a specified list of courses from overlapping in time."""

    _instance_count = 0

    def __init__(self, courses: list[str], name: str | None = None):
        self.courses = set(courses)
        NoCourseOverlap._instance_count += 1
        self._id = NoCourseOverlap._instance_count
        display_name = name if name else ', '.join(courses)
        super().__init__(name=f"No overlap for courses ({display_name})")

    def apply(self, scheduler) -> int:
        day_start_pairs = scheduler.get_day_start_pairs()

        count = 0
        for day, start_minutes in day_start_pairs:
            overlapping_keys = [
                k for k in scheduler.keys
                if k[0] in self.courses
                and scheduler.slot_overlaps(k[2], day, start_minutes)
            ]

            if overlapping_keys:
                scheduler.prob += (
                    lpSum(scheduler.x[k] for k in overlapping_keys) <= 1,
                    f"no_course_overlap_{self._id}_{day}_{start_minutes}"
                )
                count += 1
        return count


class SameTimeSlot(ConstraintBase):
    """Forces a specified list of courses to be scheduled in the same time slot."""

    _instance_count = 0

    def __init__(self, courses: list[str], name: str | None = None):
        self.courses = list(courses)
        SameTimeSlot._instance_count += 1
        self._id = SameTimeSlot._instance_count
        display_name = name if name else ', '.join(courses)
        super().__init__(name=f"Same time slot for courses ({display_name})")

    def apply(self, scheduler) -> int:
        if len(self.courses) < 2:
            return 0

        count = 0
        first_course = self.courses[0]

        # For each time slot, if the first course is assigned to it,
        # then all other courses must also be assigned to that time slot
        for time_slot in scheduler.time_slots:
            first_keys = filter_keys(scheduler.keys, course=first_course, time_slot=time_slot)
            if not first_keys:
                continue

            # Sum of first course's assignments to this time slot (across all rooms)
            first_sum = lpSum(scheduler.x[k] for k in first_keys)

            for other_course in self.courses[1:]:
                other_keys = filter_keys(scheduler.keys, course=other_course, time_slot=time_slot)
                if not other_keys:
                    continue

                # Sum of other course's assignments to this time slot (across all rooms)
                other_sum = lpSum(scheduler.x[k] for k in other_keys)

                # If first course is in this slot, other course must be too
                scheduler.prob += (
                    first_sum == other_sum,
                    f"same_time_slot_{self._id}_{first_course}_{other_course}_{time_slot}"
                )
                count += 1

        return count

