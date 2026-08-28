#!/usr/bin/env python3
"""
Example objective classes for schedule optimization.

These demonstrate common scheduling objectives that can be combined
in different orders to create customized optimization strategies.
"""

from .objective_base import ObjectiveBase
from pulp import lpSum, LpAffineExpression, LpVariable
from .scheduler import filter_keys
from .utils import time_to_minutes
from typing import Optional, List
import pandas as pd


def _format_list_summary(items: list) -> str:
    """Format a list of items as 'item1 and N others' or 'item1, item2' for short lists."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{items[0]} and {len(items) - 1} others"


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
        courses: Optional[list[str]] = None,
        days: Optional[list[str]] = None,
        sense: str = 'minimize',
        tolerance: float = 0.0,
        warn_missing: bool = True
    ):
        """
        Args:
            time: Time in HH:MM format (e.g., "9:00")
            instructor: If specified, only count this instructor's classes
            courses: If specified, only count these courses
            days: If specified, only count classes on these days (e.g., ['M', 'W', 'F'])
            sense: 'minimize' or 'maximize'
            tolerance: Fractional tolerance for lexicographic constraint
            warn_missing: Warn about named courses that are not being scheduled
        """
        self.time = time
        self.time_minutes = time_to_minutes(time)
        self.instructor = instructor
        self.courses = set(courses) if courses else None
        self.days = set(days) if days else None
        self.warn_missing = warn_missing

        name_parts = [f"classes before {time}"]
        if instructor:
            name_parts.append(f"for {instructor}")
        if days:
            name_parts.append(f"on {','.join(sorted(days))}")

        super().__init__(
            name=f"{sense.capitalize()} {' '.join(name_parts)}",
            sense=sense,
            tolerance=tolerance
        )

    def evaluate(self, scheduler):
        self._warn_once_about_missing_courses(scheduler)

        def matches_criteria(course, room, time_slot):
            # Check time constraint
            slot_start = scheduler.slot_start_minutes[time_slot]
            if slot_start >= self.time_minutes:
                return False

            # Check days constraint
            if self.days:
                slot_days = scheduler.slot_days[time_slot]
                if not slot_days.intersection(self.days):
                    return False

            # Check instructor constraint
            if self.instructor:
                if self.instructor not in scheduler.course_instructors[course]:
                    return False

            # Check course constraint
            if self.courses and course not in self.courses:
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
        courses: Optional[list[str]] = None,
        course_type: Optional[str] = None,
        days: Optional[list[str]] = None,
        sense: str = 'minimize',
        tolerance: float = 0.0,
        warn_missing: bool = True
    ):
        """
        Args:
            time: Time in HH:MM format (e.g., "16:00")
            instructor: If specified, only count this instructor's classes
            courses: If specified, only count these courses
            course_type: If specified, only count this type ('Lecture' or 'Lab')
            days: If specified, only count classes on these days (e.g., ['M', 'W', 'F'])
            sense: 'minimize' or 'maximize'
            tolerance: Fractional tolerance for lexicographic constraint
            warn_missing: Warn about named courses that are not being scheduled
        """
        self.time = time
        self.time_minutes = time_to_minutes(time)
        self.instructor = instructor
        self.courses = set(courses) if courses else None
        self.course_type = course_type
        self.days = set(days) if days else None
        self.warn_missing = warn_missing

        name_parts = [f"classes after {time}"]
        if instructor:
            name_parts.append(f"for {instructor}")
        if courses:
            name_parts.append(f"for {_format_list_summary(list(courses))}")
        if course_type:
            name_parts.append(f"({course_type})")
        if days:
            name_parts.append(f"on {','.join(sorted(days))}")

        super().__init__(
            name=f"{sense.capitalize()} {' '.join(name_parts)}",
            sense=sense,
            tolerance=tolerance
        )

    def evaluate(self, scheduler):
        self._warn_once_about_missing_courses(scheduler)

        def matches_criteria(course, room, time_slot):
            # Check time constraint (use end time to catch classes running past the threshold)
            slot_end = scheduler.slot_end_minutes[time_slot]
            if slot_end <= self.time_minutes:
                return False

            # Check days constraint
            if self.days:
                slot_days = scheduler.slot_days[time_slot]
                if not slot_days.intersection(self.days):
                    return False

            # Check instructor constraint
            if self.instructor:
                if self.instructor not in scheduler.course_instructors[course]:
                    return False

            # Check course constraint
            if self.courses and course not in self.courses:
                return False

            # Check course type constraint
            if self.course_type:
                if scheduler.course_slot_type[course] != self.course_type:
                    return False

            return True

        filtered = filter_keys(scheduler.keys, predicate=matches_criteria)
        return lpSum(scheduler.x[k] for k in filtered)


class MinimizeMinutesAfter(ObjectiveBase):
    """
    Minimize total minutes of class time scheduled after a given time.

    Unlike MinimizeClassesAfter which counts the number of classes,
    this counts the actual minutes past the threshold. Useful for
    soft preferences where some overage is acceptable but should be minimized.
    """

    def __init__(self, time: str, tolerance: float = 0.0):
        """
        Args:
            time: Time in HH:MM format (e.g., "16:00")
            tolerance: Fractional tolerance for lexicographic constraint
        """
        self.time_minutes = time_to_minutes(time)

        super().__init__(
            name=f"Minimize minutes after {time}",
            sense='minimize',
            tolerance=tolerance
        )

    def evaluate(self, scheduler):
        terms = []
        for course, room, time_slot in scheduler.keys:
            slot_end = scheduler.slot_end_minutes[time_slot]
            if slot_end > self.time_minutes:
                minutes_after = slot_end - self.time_minutes
                num_days = len(scheduler.slot_days[time_slot])
                terms.append(minutes_after * num_days * scheduler.x[(course, room, time_slot)])

        if not terms:
            return LpAffineExpression()
        return lpSum(terms)


class MaximizeClassesInSlots(ObjectiveBase):
    """
    Maximize classes scheduled in a specific set of time slots.

    Useful for maximizing classes in particular time slots,
    such as prime-time slots or preferred scheduling windows.
    """

    def __init__(
        self,
        slots: List[str],
        instructor: Optional[str] = None,
        courses: Optional[List[str]] = None,
        course_type: Optional[str] = None,
        tolerance: float = 0.0,
        name: Optional[str] = None,
        warn_missing: bool = True
    ):
        """
        Args:
            slots: List of time slot names to count (e.g., ["MWF 9:00", "MWF 10:00"])
            instructor: If specified, only count this instructor's classes
            courses: If specified, only count these courses
            course_type: If specified, only count this type ('Lecture' or 'Lab')
            tolerance: Fractional tolerance for lexicographic constraint
            name: Optional custom name for the objective
            warn_missing: Warn about named courses that are not being scheduled
        """
        self.slots = set(slots)
        self.instructor = instructor
        self.courses = set(courses) if courses else None
        self.course_type = course_type
        self.warn_missing = warn_missing

        if name is None:
            name_parts = [f"classes in {len(slots)} slot(s)"]
            if instructor:
                name_parts.append(f"for {instructor}")
            if courses:
                name_parts.append(f"for {_format_list_summary(list(courses))}")
            if course_type:
                name_parts.append(f"({course_type})")
            name = f"Maximize {' '.join(name_parts)}"

        super().__init__(
            name=name,
            sense='maximize',
            tolerance=tolerance
        )

    def evaluate(self, scheduler):
        self._warn_once_about_missing_courses(scheduler)

        def matches_criteria(course, room, time_slot):
            # Check slot constraint
            if time_slot not in self.slots:
                return False

            # Check instructor constraint
            if self.instructor:
                if self.instructor not in scheduler.course_instructors[course]:
                    return False

            # Check course constraint
            if self.courses and course not in self.courses:
                return False

            # Check course type constraint
            if self.course_type:
                if scheduler.course_slot_type[course] != self.course_type:
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
        courses: Optional[List[str]] = None,
        course_type: Optional[str] = None,
        tolerance: float = 0.0,
        warn_missing: bool = True
    ):
        """
        Args:
            preferred_rooms: List of room names to prefer
            instructor: If specified, only for this instructor's classes
            courses: If specified, only for these specific courses
            course_type: If specified, only for this type ('Lecture' or 'Lab')
            tolerance: Fractional tolerance for lexicographic constraint
            warn_missing: Warn about named courses that are not being scheduled
        """
        self.preferred_rooms = set(preferred_rooms)
        self.instructor = instructor
        self.courses = set(courses) if courses else None
        self.course_type = course_type
        self.warn_missing = warn_missing

        name_parts = [f"preferred rooms ({', '.join(preferred_rooms)})"]
        if instructor:
            name_parts.append(f"for {instructor}")
        if courses:
            name_parts.append(f"for {_format_list_summary(list(courses))}")
        if course_type:
            name_parts.append(f"({course_type})")

        super().__init__(
            name=f"Maximize {' '.join(name_parts)}",
            sense='maximize',
            tolerance=tolerance
        )

    def evaluate(self, scheduler):
        self._warn_once_about_missing_courses(scheduler)

        def matches_criteria(course, room, time_slot):
            # Check room constraint
            if room not in self.preferred_rooms:
                return False

            # Check instructor constraint
            if self.instructor:
                if self.instructor not in scheduler.course_instructors[course]:
                    return False

            # Check courses constraint
            if self.courses and course not in self.courses:
                return False

            # Check course type constraint
            if self.course_type:
                if scheduler.course_slot_type[course] != self.course_type:
                    return False

            return True

        filtered = filter_keys(scheduler.keys, predicate=matches_criteria)
        return lpSum(scheduler.x[k] for k in filtered)


class MinimizePreferredRooms(ObjectiveBase):
    """
    Minimize use of specific rooms.

    Useful for avoiding overflow rooms or locations that should be last-resort.
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
            preferred_rooms: List of room names to avoid
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
            name=f"Minimize {' '.join(name_parts)}",
            sense='minimize',
            tolerance=tolerance
        )

    def evaluate(self, scheduler):
        def matches_criteria(course, room, time_slot):
            if room not in self.preferred_rooms:
                return False

            if self.instructor:
                if self.instructor not in scheduler.course_instructors[course]:
                    return False

            if self.course_type:
                if scheduler.course_slot_type[course] != self.course_type:
                    return False

            return True

        filtered = filter_keys(scheduler.keys, predicate=matches_criteria)
        return lpSum(scheduler.x[k] for k in filtered)




class MinimizeRoomOrderByCourseRank(ObjectiveBase):
    """
    Minimize room-name order weighted by per-course rank.

    Uses a numeric Rank column from courses.csv (higher rank = stronger preference).
    Rooms are ordered lexicographically by name, and assignments to "later" rooms
    are penalized in proportion to course rank.
    """

    def __init__(
        self,
        rank_column: str = "Rank",
        tolerance: float = 0.0
    ):
        """
        Args:
            rank_column: Column in courses.csv containing numeric ranks
            tolerance: Fractional tolerance for lexicographic constraint
        """
        self.rank_column = rank_column

        super().__init__(
            name=f"Minimize room order by course rank ({rank_column})",
            sense='minimize',
            tolerance=tolerance
        )

    def evaluate(self, scheduler):
        if self.rank_column not in scheduler.courses_df.columns:
            return LpAffineExpression()

        ranks = dict(zip(scheduler.courses_df['Course'], scheduler.courses_df[self.rank_column]))
        room_order = {room: idx for idx, room in enumerate(sorted(scheduler.rooms))}

        def to_weight(value):
            if value is None:
                return 0.0
            try:
                weight = float(value)
            except (TypeError, ValueError):
                return 0.0
            if weight != weight:  # NaN check
                return 0.0
            return weight

        terms = []
        for course, room, time_slot in scheduler.keys:
            weight = to_weight(ranks.get(course))
            if weight > 0:
                terms.append(weight * room_order[room] * scheduler.x[(course, room, time_slot)])

        if not terms:
            return LpAffineExpression()
        return lpSum(terms)


class MaximizeBackToBackCourses(ObjectiveBase):
    """
    Maximize back-to-back placement for a specified set of courses.

    This objective rewards adjacent time slots (by start time) that are
    assigned to different courses in the specified list. Adjacency is
    evaluated within the same slot type and same days set.

    Courses that are not being scheduled (ignored or not offered) are dropped
    with a warning; with fewer than two left there is nothing to place
    back-to-back and the objective is constant. Pass warn_missing=False for a
    list that is deliberately carried between semesters and only partially
    offered in any one of them.
    """

    _instance_count = 0

    def __init__(
        self,
        courses: List[str],
        same_room: bool = False,
        tolerance: float = 0.0,
        warn_missing: bool = True
    ):
        """
        Args:
            courses: List of course names to cluster back-to-back.
            same_room: If True, only count adjacency when both courses are in the same room.
            tolerance: Fractional tolerance for lexicographic constraint.
            warn_missing: Warn about named courses that are not being scheduled
        """
        self.courses = list(courses)
        self.same_room = same_room
        self.warn_missing = warn_missing
        self._built = False
        self._objective_expr = None

        MaximizeBackToBackCourses._instance_count += 1
        self._id = MaximizeBackToBackCourses._instance_count

        super().__init__(
            name=f"Maximize back-to-back for {_format_list_summary(self.courses)}",
            sense='maximize',
            tolerance=tolerance
        )

    def _build(self, scheduler):
        courses = scheduler.resolve_courses(self.courses, self.name, warn=self.warn_missing)
        if len(courses) < 2:
            if self.warn_missing:
                print(f"Warning: {self.name} has fewer than two courses left to schedule; "
                      f"there is nothing to place back-to-back")
            self._objective_expr = LpAffineExpression()
            self._built = True
            return

        # Group time slots by slot type and days set
        groups = {}
        for slot in scheduler.time_slots:
            slot_type = scheduler.slot_type[slot]
            days_key = tuple(sorted(scheduler.slot_days[slot]))
            key = (slot_type, days_key)
            groups.setdefault(key, []).append(slot)

        # Build adjacency list of consecutive (slot1, slot2) pairs
        adjacent_slots = []
        for slots in groups.values():
            slots_sorted = sorted(slots, key=lambda s: scheduler.slot_start_minutes[s])
            for i in range(len(slots_sorted) - 1):
                s1 = slots_sorted[i]
                s2 = slots_sorted[i + 1]
                adjacent_slots.append((s1, s2))

        # Precompute course-slot assignment expressions (summing over rooms)
        course_slot_expr = {}
        for course in courses:
            for slot in scheduler.time_slots:
                keys = filter_keys(scheduler.keys, course=course, time_slot=slot)
                if keys:
                    course_slot_expr[(course, slot)] = lpSum(scheduler.x[k] for k in keys)

        # Precompute course-slot-room expressions when same_room is required
        course_slot_room_expr = {}
        if self.same_room:
            for course in courses:
                for slot in scheduler.time_slots:
                    for room in scheduler.rooms:
                        keys = filter_keys(scheduler.keys, course=course, room=room, time_slot=slot)
                        if keys:
                            course_slot_room_expr[(course, slot, room)] = lpSum(scheduler.x[k] for k in keys)

        adjacency_vars = []
        var_count = 0
        for i, course_a in enumerate(courses):
            for course_b in courses[i + 1:]:
                for s1, s2 in adjacent_slots:
                    if self.same_room:
                        for room in scheduler.rooms:
                            # course_a in s1 AND course_b in s2 (same room)
                            if (course_a, s1, room) in course_slot_room_expr and (course_b, s2, room) in course_slot_room_expr:
                                y = LpVariable(f"bb_{self._id}_{var_count}", cat='Binary')
                                scheduler.prob += (y <= course_slot_room_expr[(course_a, s1, room)], f"bb_{self._id}_{var_count}_ub1")
                                scheduler.prob += (y <= course_slot_room_expr[(course_b, s2, room)], f"bb_{self._id}_{var_count}_ub2")
                                scheduler.prob += (
                                    y >= course_slot_room_expr[(course_a, s1, room)] + course_slot_room_expr[(course_b, s2, room)] - 1,
                                    f"bb_{self._id}_{var_count}_lb"
                                )
                                adjacency_vars.append(y)
                                var_count += 1

                            # course_a in s2 AND course_b in s1 (same room, reverse)
                            if (course_a, s2, room) in course_slot_room_expr and (course_b, s1, room) in course_slot_room_expr:
                                y = LpVariable(f"bb_{self._id}_{var_count}", cat='Binary')
                                scheduler.prob += (y <= course_slot_room_expr[(course_a, s2, room)], f"bb_{self._id}_{var_count}_ub1")
                                scheduler.prob += (y <= course_slot_room_expr[(course_b, s1, room)], f"bb_{self._id}_{var_count}_ub2")
                                scheduler.prob += (
                                    y >= course_slot_room_expr[(course_a, s2, room)] + course_slot_room_expr[(course_b, s1, room)] - 1,
                                    f"bb_{self._id}_{var_count}_lb"
                                )
                                adjacency_vars.append(y)
                                var_count += 1
                    else:
                        # course_a in s1 AND course_b in s2
                        if (course_a, s1) in course_slot_expr and (course_b, s2) in course_slot_expr:
                            y = LpVariable(f"bb_{self._id}_{var_count}", cat='Binary')
                            scheduler.prob += (y <= course_slot_expr[(course_a, s1)], f"bb_{self._id}_{var_count}_ub1")
                            scheduler.prob += (y <= course_slot_expr[(course_b, s2)], f"bb_{self._id}_{var_count}_ub2")
                            scheduler.prob += (
                                y >= course_slot_expr[(course_a, s1)] + course_slot_expr[(course_b, s2)] - 1,
                                f"bb_{self._id}_{var_count}_lb"
                            )
                            adjacency_vars.append(y)
                            var_count += 1

                        # course_a in s2 AND course_b in s1 (reverse order)
                        if (course_a, s2) in course_slot_expr and (course_b, s1) in course_slot_expr:
                            y = LpVariable(f"bb_{self._id}_{var_count}", cat='Binary')
                            scheduler.prob += (y <= course_slot_expr[(course_a, s2)], f"bb_{self._id}_{var_count}_ub1")
                            scheduler.prob += (y <= course_slot_expr[(course_b, s1)], f"bb_{self._id}_{var_count}_ub2")
                            scheduler.prob += (
                                y >= course_slot_expr[(course_a, s2)] + course_slot_expr[(course_b, s1)] - 1,
                                f"bb_{self._id}_{var_count}_lb"
                            )
                            adjacency_vars.append(y)
                            var_count += 1

        if adjacency_vars:
            self._objective_expr = lpSum(adjacency_vars)
        else:
            self._objective_expr = LpAffineExpression()
        self._built = True

    def evaluate(self, scheduler):
        if not self._built:
            self._build(scheduler)
        return self._objective_expr


class MinimizeBackToBack(ObjectiveBase):
    """
    Minimize back-to-back teaching assignments for all instructors.

    Counts pairs of consecutive course assignments for each instructor
    and minimizes the total. This helps ensure instructors have breaks
    between classes.
    """

    _instance_count = 0

    def __init__(self, tolerance: float = 0.0):
        """
        Args:
            tolerance: Fractional tolerance for lexicographic constraint.
        """
        self._built = False
        self._objective_expr = None

        MinimizeBackToBack._instance_count += 1
        self._id = MinimizeBackToBack._instance_count

        super().__init__(
            name="Minimize back-to-back teaching",
            sense='minimize',
            tolerance=tolerance
        )

    def _build(self, scheduler):
        # Build instructor -> courses mapping
        instructor_courses = {}
        for course in scheduler.courses:
            for instructor in scheduler.course_instructors[course]:
                instructor_courses.setdefault(instructor, []).append(course)

        # Group time slots by slot type and days set (same as MaximizeBackToBackCourses)
        groups = {}
        for slot in scheduler.time_slots:
            slot_type = scheduler.slot_type[slot]
            days_key = tuple(sorted(scheduler.slot_days[slot]))
            key = (slot_type, days_key)
            groups.setdefault(key, []).append(slot)

        # Build adjacency list of consecutive (slot1, slot2) pairs
        adjacent_slots = []
        for slots in groups.values():
            slots_sorted = sorted(slots, key=lambda s: scheduler.slot_start_minutes[s])
            for i in range(len(slots_sorted) - 1):
                s1 = slots_sorted[i]
                s2 = slots_sorted[i + 1]
                adjacent_slots.append((s1, s2))

        # Precompute course-slot assignment expressions (summing over rooms)
        course_slot_expr = {}
        for course in scheduler.courses:
            for slot in scheduler.time_slots:
                keys = filter_keys(scheduler.keys, course=course, time_slot=slot)
                if keys:
                    course_slot_expr[(course, slot)] = lpSum(scheduler.x[k] for k in keys)

        # Create binary variables for back-to-back pairs per instructor
        adjacency_vars = []
        var_count = 0

        for instructor, courses in instructor_courses.items():
            # For each ordered pair of courses (including same course twice)
            for course_a in courses:
                for course_b in courses:
                    for s1, s2 in adjacent_slots:
                        # course_a in s1 AND course_b in s2
                        if (course_a, s1) in course_slot_expr and (course_b, s2) in course_slot_expr:
                            y = LpVariable(f"mbb_{self._id}_{var_count}", cat='Binary')
                            scheduler.prob += (y <= course_slot_expr[(course_a, s1)], f"mbb_{self._id}_{var_count}_ub1")
                            scheduler.prob += (y <= course_slot_expr[(course_b, s2)], f"mbb_{self._id}_{var_count}_ub2")
                            scheduler.prob += (
                                y >= course_slot_expr[(course_a, s1)] + course_slot_expr[(course_b, s2)] - 1,
                                f"mbb_{self._id}_{var_count}_lb"
                            )
                            adjacency_vars.append(y)
                            var_count += 1

        if adjacency_vars:
            self._objective_expr = lpSum(adjacency_vars)
        else:
            self._objective_expr = LpAffineExpression()
        self._built = True

    def evaluate(self, scheduler):
        if not self._built:
            self._build(scheduler)
        return self._objective_expr


class TargetFill(ObjectiveBase):
    """
    Penalize room assignments based on how far they are from a target fill ratio.

    For each assignment, computes the squared difference between the actual fill
    ratio (enrollment / capacity) and the target fill ratio. Using fractional
    units ensures that large and small rooms have equal weight in the objective.
    This encourages placing courses in rooms where they'll fill to approximately
    the target percentage.
    """

    def __init__(self, target_fill_ratio: float = 0.75, tolerance: float = 0.0):
        """
        Args:
            target_fill_ratio: Target fill ratio (0.0 to 1.0). Default 0.75 means
                rooms should ideally be 75% full.
            tolerance: Fractional tolerance for lexicographic constraint.
        """
        self.target_fill_ratio = target_fill_ratio

        super().__init__(
            name=f"Target fill ratio ({target_fill_ratio*100:.0f}%)",
            sense='minimize',
            tolerance=tolerance
        )

    def evaluate(self, scheduler):
        terms = []
        for course, room, time_slot in scheduler.keys:
            enrollment = scheduler.enrollments[course]
            capacity = scheduler.capacities[room]

            # Calculate actual fill ratio and target fill ratio
            actual_fill = enrollment / capacity

            # Squared difference penalty (in fractional units)
            # This ensures large and small rooms have equal weight
            penalty = (actual_fill - self.target_fill_ratio) ** 2

            terms.append(penalty * scheduler.x[(course, room, time_slot)])

        if not terms:
            return LpAffineExpression()
        return lpSum(terms)


class MinimizeScheduleChanges(ObjectiveBase):
    """
    Minimize changes from a previous schedule.

    Penalizes assignments that differ from a reference schedule, allowing
    incremental adjustments while keeping most courses in their original
    time slots and rooms. Supports per-course weights to prioritize keeping
    certain courses unchanged.
    """

    def __init__(
        self,
        previous_schedule,
        weights: Optional[dict[str, float]] = None,
        weight_column: str = 'Change Weight',
        time_only: bool = False,
        tolerance: float = 0.0
    ):
        """
        Args:
            previous_schedule: Either a path to a CSV file or a DataFrame with columns
                              ['Course', 'Room', 'Slot'] for the reference schedule.
            weights: Optional dict mapping course names to weights (default 1.0).
                    Higher weights make it more important to keep that course unchanged.
                    Example: {'MATH-101': 5.0, 'PHYS-201': 2.0}
            weight_column: Column name in the schedule file/DataFrame containing
                          per-course weights. Default is 'Change Weight'. If both weights
                          dict and weight_column are provided, the dict takes precedence.
            time_only: If True, only penalize changes to the time slot, ignoring room changes.
            tolerance: Fractional tolerance for lexicographic constraint.
        """
        # Load from file if string path provided
        if isinstance(previous_schedule, str):
            previous_schedule = pd.read_csv(previous_schedule)
        elif not isinstance(previous_schedule, pd.DataFrame):
            raise TypeError("previous_schedule must be a file path or pandas DataFrame")

        required_cols = {'Course'}
        if not required_cols.issubset(previous_schedule.columns):
            raise ValueError(f"previous_schedule must have columns: {required_cols}")

        self.previous_schedule = previous_schedule
        self.weight_column = weight_column
        self.time_only = time_only

        # Build weights dict: start with column values, then override with explicit weights
        self.weights = {}
        if weight_column and weight_column in previous_schedule.columns:
            for _, row in previous_schedule.iterrows():
                if pd.notna(row[weight_column]):
                    self.weights[row['Course']] = float(row[weight_column])

        # Explicit weights dict overrides column values
        if weights:
            self.weights.update(weights)

        name = "Minimize schedule changes (time only)" if time_only else "Minimize schedule changes"
        super().__init__(
            name=name,
            sense='minimize',
            tolerance=tolerance
        )


    def evaluate(self, scheduler):
        if self.time_only:
            # Build lookup: course -> slot
            previous_slots = {}
            for _, row in self.previous_schedule.iterrows():
                previous_slots[row['Course']] = row['Slot']

            # Penalize assignments where the time slot differs
            terms = []
            for course, room, time_slot in scheduler.keys:
                if course in previous_slots and time_slot != previous_slots[course]:
                    weight = self.weights.get(course, 1.0)
                    terms.append(weight * scheduler.x[(course, room, time_slot)])
                elif course not in previous_slots:
                    # New course not in previous schedule - penalize all assignments
                    weight = self.weights.get(course, 1.0)
                    terms.append(weight * scheduler.x[(course, room, time_slot)])
        else:
            previous_assignments = set()
            for _, row in self.previous_schedule.iterrows():
                key = (row['Course'], row['Room'], row['Slot'])
                previous_assignments.add(key)

            # Penalize assignments that differ from previous schedule
            # Award 0 penalty for keeping the same assignment, weight penalty for changing
            terms = []
            for key in scheduler.keys:
                if key not in previous_assignments:
                    course = key[0]
                    weight = self.weights.get(course, 1.0)
                    terms.append(weight * scheduler.x[key])

        return lpSum(terms)


class MinimizeTeachingDaysOver(ObjectiveBase):
    """
    Minimize teaching days over a threshold for specified instructors.

    Penalizes instructors who teach on more than threshold days per week.
    Uses squared penalty: 4 days (excess=1) = penalty 1, 5 days (excess=2) = penalty 4.
    """

    _instance_count = 0

    def __init__(
        self,
        threshold: int = 3,
        instructors: Optional[List[str]] = None,
        tolerance: float = 0.0
    ):
        """
        Args:
            threshold: Maximum ideal teaching days (default 3).
            instructors: List of instructor names to apply to (e.g., ['Smith', 'Jones']).
                        If None, applies to all instructors.
            tolerance: Fractional tolerance for lexicographic constraint.
        """
        self.threshold = threshold
        self.instructors = set(instructors) if instructors else None
        self._built = False
        self._objective_expr = None

        MinimizeTeachingDaysOver._instance_count += 1
        self._id = MinimizeTeachingDaysOver._instance_count

        name_parts = [f"teaching days over {threshold}"]
        if instructors:
            name_parts.append(f"for {_format_list_summary(list(instructors))}")

        super().__init__(
            name=f"Minimize {' '.join(name_parts)}",
            sense='minimize',
            tolerance=tolerance
        )

    def _build(self, scheduler):
        # Get all unique days from time slots
        all_days = set()
        for slot in scheduler.time_slots:
            all_days.update(scheduler.slot_days[slot])
        all_days = sorted(all_days)

        # Filter instructors
        if self.instructors is None:
            target_instructors = scheduler.instructors
        else:
            target_instructors = [i for i in scheduler.instructors if i in self.instructors]

        if not target_instructors:
            self._objective_expr = LpAffineExpression()
            self._built = True
            return

        # Build instructor -> courses mapping
        instructor_courses = {}
        for course in scheduler.courses:
            for instructor in scheduler.course_instructors[course]:
                if instructor in target_instructors:
                    instructor_courses.setdefault(instructor, []).append(course)

        penalty_vars = []
        var_count = 0

        for instructor in target_instructors:
            courses = instructor_courses.get(instructor, [])
            if not courses:
                continue

            # Create binary variable for each day: teaches_on_day[day] = 1 if instructor teaches any course on that day
            teaches_on_day = {}
            for day in all_days:
                # Find all keys where this instructor's course is in a slot that includes this day
                day_keys = []
                for course in courses:
                    for c, r, t in scheduler.keys:
                        if c == course and day in scheduler.slot_days[t]:
                            day_keys.append((c, r, t))

                if not day_keys:
                    continue

                # Create binary variable: 1 if instructor teaches on this day
                y = LpVariable(f"mtdo_{self._id}_{var_count}_day", cat='Binary')
                var_count += 1

                # y >= x for each assignment on this day (if any assignment, y=1)
                for k in day_keys:
                    scheduler.prob += (y >= scheduler.x[k], f"mtdo_{self._id}_{var_count}_lb_{k[0]}_{k[2]}")
                    var_count += 1

                # y <= sum of all assignments on this day (if no assignments, y=0)
                scheduler.prob += (y <= lpSum(scheduler.x[k] for k in day_keys), f"mtdo_{self._id}_{var_count}_ub")
                var_count += 1

                teaches_on_day[day] = y

            if not teaches_on_day:
                continue

            # Total teaching days for this instructor
            total_days_expr = lpSum(teaches_on_day.values())

            # Create excess variables for squared penalty
            # excess_k = max(0, total_days - threshold - k + 1) for k = 1, 2, ...
            # This creates a piecewise linear approximation of squared penalty
            max_possible_excess = len(all_days) - self.threshold
            if max_possible_excess <= 0:
                continue

            # For squared penalty, we use: sum of excess_k for k = 1 to max_excess
            # where each excess_k = 1 if total_days >= threshold + k
            # This gives: 1 excess day = 1, 2 excess days = 1+2=3... wait, that's triangular
            # For actual squared: excess=1 -> 1, excess=2 -> 4
            # Use: sum_{k=1}^{excess} (2k-1) = excess^2
            # So we need variables that indicate if excess >= k, weighted by (2k-1)

            for k in range(1, max_possible_excess + 1):
                # excess_k = 1 if total_days >= threshold + k
                e_k = LpVariable(f"mtdo_{self._id}_{var_count}_excess", cat='Binary')
                var_count += 1

                day_threshold = self.threshold + k
                # e_k = 1 if total_days >= day_threshold
                # Constraint: e_k <= (total_days - day_threshold + len(all_days)) / len(all_days)
                # This ensures e_k can only be 1 if total_days >= day_threshold
                # And: total_days >= day_threshold * e_k
                scheduler.prob += (
                    total_days_expr >= day_threshold * e_k,
                    f"mtdo_{self._id}_{var_count}_excess_lb"
                )
                var_count += 1

                # e_k <= 1 if total_days >= day_threshold (big-M style)
                # total_days - day_threshold + M*(1-e_k) >= 0 where M = len(all_days)
                # Rearranged: total_days >= day_threshold - M + M*e_k
                # But we want: if total_days < day_threshold then e_k = 0
                # total_days <= day_threshold - 1 + M*e_k
                M = len(all_days)
                scheduler.prob += (
                    total_days_expr <= day_threshold - 1 + M * e_k,
                    f"mtdo_{self._id}_{var_count}_excess_ub"
                )
                var_count += 1

                # Weight for squared penalty: (2k - 1)
                # sum of (2k-1) for k=1 to n = n^2
                weight = 2 * k - 1
                penalty_vars.append(weight * e_k)

        if penalty_vars:
            self._objective_expr = lpSum(penalty_vars)
        else:
            self._objective_expr = LpAffineExpression()
        self._built = True

    def evaluate(self, scheduler):
        if not self._built:
            self._build(scheduler)
        return self._objective_expr
