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
    """Prevents a specified list of courses from overlapping in time.

    Courses that are not being scheduled (ignored or not offered) are dropped
    with a warning. Pass warn_missing=False for a list that is deliberately
    carried between semesters and only partially offered in any one of them.
    """

    _instance_count = 0

    def __init__(self, courses: list[str], name: str | None = None, warn_missing: bool = True):
        self.courses = set(courses)
        self.warn_missing = warn_missing
        NoCourseOverlap._instance_count += 1
        self._id = NoCourseOverlap._instance_count
        display_name = name if name else ', '.join(courses)
        super().__init__(name=f"No overlap for courses ({display_name})")

    def apply(self, scheduler) -> int:
        courses = set(scheduler.resolve_courses(
            sorted(self.courses), self.name, warn=self.warn_missing))

        day_start_pairs = scheduler.get_day_start_pairs()

        count = 0
        for day, start_minutes in day_start_pairs:
            overlapping_keys = [
                k for k in scheduler.keys
                if k[0] in courses
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
    """Forces a specified list of courses to be scheduled in the same time slot.

    Courses that are not being scheduled (ignored or not offered) are dropped
    with a warning; if fewer than two remain the constraint is skipped. Pass
    warn_missing=False for a list that is deliberately carried between semesters
    and only partially offered in any one of them.
    """

    _instance_count = 0

    def __init__(self, courses: list[str], name: str | None = None, warn_missing: bool = True):
        self.courses = list(courses)
        self.warn_missing = warn_missing
        SameTimeSlot._instance_count += 1
        self._id = SameTimeSlot._instance_count
        display_name = name if name else ', '.join(courses)
        super().__init__(name=f"Same time slot for courses ({display_name})")

    def apply(self, scheduler) -> int:
        if len(self.courses) < 2:
            return 0

        courses = scheduler.resolve_courses(self.courses, self.name, warn=self.warn_missing)
        if len(courses) < 2:
            if self.warn_missing:
                print(f"Warning: {self.name} has fewer than two courses left to schedule; "
                      f"skipping it")
            return 0

        # Validate that all courses have the same slot type
        slot_types = {scheduler.course_slot_type[c] for c in courses}

        if len(slot_types) > 1:
            course_slot_info = [f"{c} ({scheduler.course_slot_type[c]})" for c in courses]
            raise ValueError(
                f"SameTimeSlot constraint requires all courses to have the same slot type. "
                f"Got courses with different slot types: {', '.join(course_slot_info)}"
            )

        count = 0
        first_course = courses[0]

        # For each time slot, if the first course is assigned to it,
        # then all other courses must also be assigned to that time slot
        for time_slot in scheduler.time_slots:
            first_keys = filter_keys(scheduler.keys, course=first_course, time_slot=time_slot)
            if not first_keys:
                continue

            # Sum of first course's assignments to this time slot (across all rooms)
            first_sum = lpSum(scheduler.x[k] for k in first_keys)

            for other_course in courses[1:]:
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

class LimitRoomTimeSlots(ConstraintBase):
    """Restricts rooms to only be used during specific time slots.

    Reads from a column in the rooms CSV (default: 'Allowed Time Slots').
    The column should contain semicolon-separated time slot names.
    Rooms without a value in this column are unrestricted.

    Example rooms.csv:
        Room,Capacity,Room Type,Allowed Time Slots
        BLDG 120,200,Lecture,MWF-0830; MWF-0935; TTH-0830
        BLDG 111,80,Lecture,
    """

    def __init__(self, column: str = 'Allowed Time Slots'):
        self.column = column
        super().__init__(name=f"Limit room time slots ({column})")

    def apply(self, scheduler) -> int:
        df = scheduler.rooms_df
        if self.column not in df.columns:
            return 0

        count = 0
        for _, row in df.iterrows():
            room = row['Room']
            allowed_slots_str = row[self.column]

            if pd.isna(allowed_slots_str) or str(allowed_slots_str).strip() == '':
                continue

            # Parse semicolon-separated list of allowed time slots
            allowed_slots = {s.strip() for s in str(allowed_slots_str).split(';') if s.strip()}

            if not allowed_slots:
                continue

            # Disable all keys for this room that are not in allowed slots
            for k in filter_keys(scheduler.keys, room=room):
                _, _, time_slot = k
                if time_slot not in allowed_slots:
                    scheduler.x[k].upBound = 0
                    count += 1

        return count


class InstructorTravelBuffer(ConstraintBase):
    """Enforce extra travel time between two room groups for the same instructor."""
    
    _instance_count = 0

    def __init__(self, rooms_a: list[str], rooms_b: list[str], min_gap_minutes: int):
        self.rooms_a = set(rooms_a)
        self.rooms_b = set(rooms_b)
        self.min_gap_minutes = min_gap_minutes
        InstructorTravelBuffer._instance_count = 1
        self.id = InstructorTravelBuffer._instance_count
        super().__init__(name=f"Instructor travel buffer {min_gap_minutes} min")

    def _too_close(self, scheduler, slot_a: str, slot_b: str) -> bool:
        if not (scheduler.slot_days[slot_a] & scheduler.slot_days[slot_b]):
            return False

        start_a = scheduler.slot_start_minutes[slot_a]
        start_b = scheduler.slot_start_minutes[slot_b]
        end_a = scheduler.slot_end_minutes[slot_a]
        end_b = scheduler.slot_end_minutes[slot_b]

        if start_b >= end_a and start_b < end_a + self.min_gap_minutes:
            return True
        if start_a >= end_b and start_a < end_b + self.min_gap_minutes:
            return True

        return False
    
    def apply(self, scheduler) -> int:
        count = 0
        if not self.rooms_a or not self.rooms_b:
            return count
        
        course_instructors = {}

        for _, row in scheduler.courses_df.iterrows():
            course = row['Course']
            instructor = row['Instructor']
            course_instructors.setdefault(course, set()).add(instructor)

        courses_in_a = {course for course, room, _ in scheduler.keys if room in self.rooms_a}
        courses_in_b = {course for course, room, _ in scheduler.keys if room in self.rooms_b}

        instructors_with_a = set()
        instructors_with_b = set()

        for course in courses_in_a:
            instructors_with_a.update(course_instructors.get(course, set()))
        for course in courses_in_b:
            instructors_with_b.update(course_instructors.get(course,set()))

        keys_by_instructor_group_slot = {}
        for course, room, slot in scheduler.keys:
            if room in self.rooms_a:
                group = "A"
            elif room in self.rooms_b:
                group = "B"
            else:
                continue
            for instructor in course_instructors.get(course, []):
                keys_by_instructor_group_slot.setdefault((instructor, group, slot), []).append((course,room,slot))

        too_close_pairs = [
            (slot_a, slot_b)
            for slot_a in scheduler.time_slots
            for slot_b in scheduler.time_slots
            if self._too_close(scheduler, slot_a, slot_b)
        ]

        for instructor in scheduler.instructors:
            if instructor not in instructors_with_a or instructor not in instructors_with_b:
                continue

            for slot_a, slot_b in too_close_pairs:
                    
                keys_a = keys_by_instructor_group_slot.get((instructor, "A", slot_a), [])
                keys_b = keys_by_instructor_group_slot.get((instructor,"B", slot_b), [])

                if keys_a and keys_b:
                    scheduler.prob += (
                        lpSum(scheduler.x[k] for k in keys_a)
                        + lpSum(scheduler.x[k] for k in keys_b)
                        <= 1,
                        f"travel_buffer_{self.id}_{instructor}_{slot_a}_{slot_b}"
                    )
                    count += 1
        return count


class ConstrainObjective(ConstraintBase):
    """Convert any objective into a hard constraint by bounding its value.

    This constraint takes an objective and bounds its expression to a given value.
    The comparison operator defaults based on the objective's sense:
    - minimize objectives default to '<=' (at most)
    - maximize objectives default to '>=' (at least)

    Example:
        # No classes after 5pm for Smith (minimize objective, defaults to <=)
        ConstrainObjective(MinimizeClassesAfter("17:00", instructor="Smith"), 0)

        # At least 3 classes in preferred rooms (maximize objective, defaults to >=)
        ConstrainObjective(MaximizePreferredRooms(["Room A", "Room B"]), 3)

        # Exactly 2 classes before 9am (explicit comparison)
        ConstrainObjective(MinimizeClassesBefore("9:00"), 2, comparison='==')
    """

    _instance_count = 0

    def __init__(self, objective, value, comparison=None):
        """
        Args:
            objective: An ObjectiveBase instance
            value: The bound value for the objective
            comparison: '<=' (at most), '>=' (at least), or '==' (exact)
                        Defaults based on sense: minimize -> '<=', maximize -> '>='
        """
        self.objective = objective
        self.value = value

        if comparison is None:
            self.comparison = '<=' if objective.sense == 'minimize' else '>='
        else:
            if comparison not in ('<=', '>=', '=='):
                raise ValueError(f"comparison must be '<=', '>=', or '==', got '{comparison}'")
            self.comparison = comparison

        ConstrainObjective._instance_count += 1
        self._id = ConstrainObjective._instance_count

        comparison_desc = {'<=': 'at most', '>=': 'at least', '==': 'exactly'}[self.comparison]
        super().__init__(name=f"Constrain {objective.name} to {comparison_desc} {value}")

    def apply(self, scheduler) -> int:
        expr = self.objective.evaluate(scheduler)

        if self.comparison == '<=':
            scheduler.prob += (
                expr <= self.value,
                f"constrain_objective_{self._id}"
            )
        elif self.comparison == '>=':
            scheduler.prob += (
                expr >= self.value,
                f"constrain_objective_{self._id}"
            )
        else:  # '=='
            scheduler.prob += (
                expr == self.value,
                f"constrain_objective_{self._id}"
            )

        return 1

