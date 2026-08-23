#!/usr/bin/env python3
"""
Instructor Scheduling System with Integer Linear Programming
Optimizes assignment of instructors to rooms considering capacity constraints.
"""

import pandas as pd
import numpy as np
from pulp import *
import csv
from typing import Dict, List, Tuple, Optional, Callable, Iterable
from .visualize_schedule import visualize_schedule
from .utils import time_to_minutes, expand_days
from .objective_base import ObjectiveBase
from .constraint_base import ConstraintBase


def parse_semicolon_list(value: str) -> List[str]:
    """Parse semicolon-separated string into list of stripped values."""
    if pd.isna(value) or not str(value).strip():
        return []
    return [item.strip() for item in str(value).split(';') if item.strip()]


# Sentinel value for "match all" in filter_keys
ALL = object()


def filter_keys(
    keys: Iterable[Tuple[str, str, str]],
    course: str | object = ALL,
    room: str | object = ALL,
    time_slot: str | object = ALL,
    predicate: Optional[Callable[[str, str, str], bool]] = None
) -> list[Tuple[str, str, str]]:
    """
    Filter scheduling keys by exact values or custom predicate.

    Args:
        keys: Iterable of (course, room, time_slot) tuples to filter (set, list, etc.)
        course: Exact course name to match, or ALL to match all courses
        room: Exact room name to match, or ALL to match all rooms
        time_slot: Exact time slot to match, or ALL to match all time slots
        predicate: Custom function (course, room, time_slot) -> bool
                   If provided, overrides exact matching parameters

    Returns:
        Filtered list of keys matching the criteria

    Examples:
        # Match all rooms/times for a specific course
        filter_keys(keys, course='DEPT-2402-001')

        # Match all courses/times for a specific room
        filter_keys(keys, room='BLDG 120')

        # Match specific course and room, all time slots
        filter_keys(keys, course='DEPT-2402-001', room='BLDG 120')

        # Match all keys (no filtering)
        filter_keys(keys)
    """
    # If predicate provided, use it exclusively
    if predicate is not None:
        return [k for k in keys if predicate(k[0], k[1], k[2])]

    # Build filter function from exact match criteria
    def matches(c: str, r: str, t: str) -> bool:
        if course is not ALL and c != course:
            return False
        if room is not ALL and r != room:
            return False
        if time_slot is not ALL and t != time_slot:
            return False
        return True

    return [k for k in keys if matches(k[0], k[1], k[2])]


class InstructorScheduler:
    def __init__(self, solver_verbose: bool = False, objective_timeout: float | None = None):
        """
        Initialize the instructor scheduler.

        Args:
            solver_verbose: If True, display solver output during optimization.
                           If False (default), solver runs silently.
            objective_timeout: Maximum seconds to spend on each objective. If None,
                              no timeout is applied.
        """
        self.time_slots_df = None
        self._constraints = []
        self.solver_verbose = solver_verbose
        self.objective_timeout = objective_timeout

    def add_constraints(self, constraints: List[ConstraintBase]):
        """
        Add constraints to be applied during problem setup.

        Args:
            constraints: List of ConstraintBase instances to add

        Example:
            scheduler.add_constraints([
                CourseAssignment(),
                InstructorNoOverlap(),
                RoomNoOverlap(),
                RoomCapacity(),
            ])
        """
        for constraint in constraints:
            if not isinstance(constraint, ConstraintBase):
                raise TypeError(f"Expected ConstraintBase instance, got {type(constraint).__name__}")
            self._constraints.append(constraint)
        print(f"Added {len(constraints)} constraint(s)")

    def load_rooms(self, filename: str = 'rooms.csv'):
        """Load room data from CSV file."""
        try:
            self.rooms_df = pd.read_csv(filename)

            # Check for duplicate rooms
            rooms = self.rooms_df['Room']
            if len(rooms) != len(rooms.unique()):
                duplicates = rooms[rooms.duplicated()].unique()
                raise ValueError(f"Duplicate rooms found: {list(duplicates)}")

            print(f"Loaded {len(self.rooms_df)} rooms from {filename}")
            return self.rooms_df
        except FileNotFoundError:
            print(f"Error: {filename} not found")
            return None
        except Exception as e:
            print(f"Error loading rooms: {e}")
            return None
    
    def load_courses(self, filename: str = 'courses.csv', ignore_column: str | None = 'Ignore'):
        """Load course data from CSV file.

        Args:
            filename: Path to the CSV file containing course data.
            ignore_column: Column name to check for ignored courses. Courses with
                truthy values (TRUE, 1, yes) in this column will be excluded from
                scheduling. Defaults to 'Ignore'. Set to None to disable filtering.
        """
        try:
            self.courses_df = pd.read_csv(filename)

            strip_columns = ['Course', 'Instructor', 'Slot Type', 'Room Type', 'Force Room', 'Force Time Slot']
            for col in strip_columns:
                if col in self.courses_df.columns:
                    self.courses_df[col] = self.courses_df[col].apply(
                        lambda x: x.strip() if isinstance(x, str) else x
                    )

            # Check for duplicate courses
            courses = self.courses_df['Course']
            if len(courses) != len(courses.unique()):
                duplicates = courses[courses.duplicated()].unique()
                raise ValueError(f"Duplicate courses found: {list(duplicates)}")

            # Filter out ignored courses if ignore_column is specified and exists
            if ignore_column is not None and ignore_column in self.courses_df.columns:
                original_count = len(self.courses_df)
                # Check for truthy values (TRUE, 1, yes, case-insensitive)
                ignore_mask = self.courses_df[ignore_column].apply(
                    lambda x: pd.notna(x) and str(x).strip().lower() in ('true', '1', 'yes')
                )
                ignored = list(self.courses_df.loc[ignore_mask, 'Course'])
                self.courses_df = self.courses_df[~ignore_mask]
                ignored_count = original_count - len(self.courses_df)

                if ignored_count > 0:
                    print(f"Ignored {ignored_count} course(s) based on '{ignore_column}' column: "
                          f"{', '.join(str(c) for c in ignored)}")

            print(f"Loaded {len(self.courses_df)} courses from {filename}")
            return self.courses_df
        except FileNotFoundError:
            print(f"Error: {filename} not found")
            return None
        except Exception as e:
            print(f"Error loading courses: {e}")
            return None

    def load_time_slots(self, filename: str = 'time_slots.csv'):
        """Load time slot data from CSV file."""
        try:
            self.time_slots_df = pd.read_csv(filename)

            # Check for duplicate time slots
            slots = self.time_slots_df['Slot']
            if len(slots) != len(slots.unique()):
                duplicates = slots[slots.duplicated()].unique()
                raise ValueError(f"Duplicate time slots found: {list(duplicates)}")

            print(f"Loaded {len(self.time_slots_df)} time slots from {filename}")
            return self.time_slots_df
        except FileNotFoundError:
            print(f"Error: {filename} not found")
            return None
        except Exception as e:
            print(f"Error loading time slots: {e}")
            return None

    def resolve_courses(self, courses: Iterable[str], context: str, warn: bool = True) -> list[str]:
        """
        Narrow a list of course names to the ones actually being scheduled.

        Courses may be missing because they were marked in the ignore column or
        because they are simply not in the course list this semester. Both are
        treated the same way: the name is dropped and, unless `warn` is False,
        one warning naming all of them is printed.

        Must be called after setup_problem() has populated self.courses.

        Args:
            courses: Course names a constraint or objective refers to
            context: Name of the constraint/objective, used in the warning
            warn: If False, drop missing courses silently

        Returns:
            The subset of `courses` that is being scheduled, in the given order
        """
        available = set(self.courses)
        present = [c for c in courses if c in available]

        if warn:
            missing = [c for c in courses if c not in available]
            if missing:
                names = ', '.join(f"'{c}'" for c in missing)
                noun = "course" if len(missing) == 1 else "courses"
                print(f"Warning: {context} refers to {noun} {names}, which "
                      f"{'is' if len(missing) == 1 else 'are'} not being scheduled "
                      f"(ignored or not offered); {'it' if len(missing) == 1 else 'they'} "
                      f"will be skipped")

        return present

    def capacity_check(self) -> list[str]:
        """
        Check for common sources of infeasibility.

        Performs two checks:
        1. Slot availability: For each (slot type, room type) combination, verifies
           there are enough (time slot, room) pairs for all courses requiring them.
        2. Enrollment capacity: For each room type, checks that courses can be
           accommodated by available room capacities. Works through capacity
           thresholds from largest to smallest, ensuring courses requiring large
           rooms don't exceed the available (slot, room) pairs.

        Returns:
            List of warning messages for potential infeasibility issues.
            Empty list if no issues are detected.

        Raises:
            ValueError: If required data (courses, rooms, or time slots) is not loaded.
        """
        if self.courses_df is None:
            raise ValueError("Course data must be loaded first")
        if self.rooms_df is None:
            raise ValueError("Room data must be loaded first")
        if self.time_slots_df is None:
            raise ValueError("Time slot data must be loaded first")

        warnings = []

        # Count time slots per slot type
        slot_type_counts = self.time_slots_df['Slot Type'].value_counts().to_dict()

        # === Check 1: Slot availability ===
        # Count courses per (slot type, room type) pair
        course_type_counts = (
            self.courses_df.groupby(['Slot Type', 'Room Type'])
            .size()
            .to_dict()
        )

        # Parse room types for each room (rooms can have multiple types)
        room_type_lists = {
            row['Room']: parse_semicolon_list(row['Room Type'])
            for _, row in self.rooms_df.iterrows()
        }

        # Count rooms per room type (a room with "Lecture; Lab" counts for both)
        room_type_counts = {}
        for room_types in room_type_lists.values():
            for rt in room_types:
                room_type_counts[rt] = room_type_counts.get(rt, 0) + 1

        # Check each (slot type, room type) combination that has courses
        for (slot_type, room_type), course_count in course_type_counts.items():
            slot_count = slot_type_counts.get(slot_type, 0)
            room_count = room_type_counts.get(room_type, 0)
            pair_count = slot_count * room_count

            if course_count > pair_count:
                msg = (
                    f"Slot type '{slot_type}' with room type '{room_type}': "
                    f"{course_count} courses but only {pair_count} (time slot, room) "
                    f"pairs available ({slot_count} slots × {room_count} rooms)"
                )
                warnings.append(msg)

        # === Check 2: Enrollment capacity ===
        # For each (slot type, room type), check that large courses can fit
        for (slot_type, room_type) in course_type_counts.keys():
            # Get courses of this type, sorted by enrollment descending
            courses_of_type = self.courses_df[
                (self.courses_df['Slot Type'] == slot_type) &
                (self.courses_df['Room Type'] == room_type)
            ].sort_values('Enrollment', ascending=False)

            # Get rooms that support this type, sorted by capacity descending
            rooms_of_type = self.rooms_df[
                self.rooms_df['Room'].apply(lambda r: room_type in room_type_lists[r])
            ].sort_values('Capacity', ascending=False)

            if rooms_of_type.empty:
                continue

            # Get unique room capacities (descending)
            capacities = rooms_of_type['Capacity'].unique()
            num_slots = slot_type_counts.get(slot_type, 0)

            # Check each capacity threshold
            for capacity in capacities:
                # Count courses that require at least this capacity
                courses_needing = (courses_of_type['Enrollment'] > capacity).sum()
                # This is actually courses that are LARGER than this capacity,
                # meaning they need a room bigger than this one

                # Count rooms with capacity > this threshold
                rooms_available = (rooms_of_type['Capacity'] > capacity).sum()
                pairs_available = rooms_available * num_slots

                if courses_needing > pairs_available:
                    msg = (
                        f"Slot type '{slot_type}', room type '{room_type}': "
                        f"{courses_needing} courses with enrollment > {capacity} but only "
                        f"{pairs_available} (slot, room) pairs with capacity > {capacity} "
                        f"({rooms_available} rooms × {num_slots} slots)"
                    )
                    warnings.append(msg)

            # Also check if any course exceeds the largest room
            max_capacity = capacities[0]
            courses_too_large = courses_of_type[courses_of_type['Enrollment'] > max_capacity]
            for _, course in courses_too_large.iterrows():
                msg = (
                    f"Course '{course['Course']}' has enrollment {course['Enrollment']} "
                    f"but largest '{room_type}' room has capacity {max_capacity}"
                )
                warnings.append(msg)

        return warnings

    def setup_problem(self):
        """
        Set up the ILP problem with variables and constraints.

        This creates the optimization problem structure without solving it,
        making variables and constraints available for objective evaluation.

        Should be called before optimize_schedule() or lexicographic_optimize().
        """
        if self.rooms_df is None or self.courses_df is None:
            print("Error: Room and course data must be loaded first")
            return False

        if self.time_slots_df is None:
            print("Error: Time slot data must be loaded first")
            return False

        # Run capacity check
        warnings = self.capacity_check()
        for warning in warnings:
            print(f"Warning: {warning}")

        # Create the constraint satisfaction problem
        self.prob = LpProblem("Instructor_Scheduling", LpMinimize)

        # Extract input parameters (store as instance variables for objectives)
        self.courses = list(self.courses_df['Course'])
        self.rooms = list(self.rooms_df['Room'])
        self.time_slots = list(self.time_slots_df['Slot'])

        # Parse instructors for each course (supports multiple instructors per course)
        self.course_instructors = {}
        for _, row in self.courses_df.iterrows():
            self.course_instructors[row['Course']] = parse_semicolon_list(row['Instructor'])

        # Extract unique instructors from all courses
        all_instructors = set()
        for instructors in self.course_instructors.values():
            all_instructors.update(instructors)
        self.instructors = list(all_instructors)

        # Create dictionaries for enrollments and capacities
        self.enrollments = dict(zip(self.courses_df['Course'], self.courses_df['Enrollment']))
        self.capacities = dict(zip(self.rooms_df['Room'], self.rooms_df['Capacity']))

        # Create dictionaries for course and time slot types
        self.course_slot_type = dict(zip(self.courses_df['Course'], self.courses_df['Slot Type']))
        self.slot_type = dict(zip(self.time_slots_df['Slot'], self.time_slots_df['Slot Type']))

        # Create dictionaries for course and room types
        # Courses have a single room type, rooms can have multiple types (semicolon-separated)
        self.course_room_type = dict(zip(self.courses_df['Course'], self.courses_df['Room Type']))
        self.room_types = {}
        for _, row in self.rooms_df.iterrows():
            self.room_types[row['Room']] = parse_semicolon_list(row['Room Type'])

        # Create matrix a; a[(instructor, course)] = 1 if instructor teaches course
        self.a = {}
        for instructor in self.instructors:
            for course in self.courses:
                if instructor in self.course_instructors[course]:
                    self.a[(instructor, course)] = 1
                else:
                    self.a[(instructor, course)] = 0

        # Create binary decision variables using LpVariable.dicts
        # x[(course, room, time)] = 1 if course is assigned to room at time slot
        # Only create variables where course slot type matches time slot type
        # and course room type is in the room's list of types
        self.keys = set([
            (course, room, t)
            for course in self.courses
            for room in self.rooms
            for t in self.time_slots
            if self.course_slot_type[course] == self.slot_type[t]
            and self.course_room_type[course] in self.room_types[room]
        ])
        self.x = LpVariable.dicts("x", list(self.keys), cat='Binary')

        course_key_counts = {course: 0 for course in self.courses}
        for course, _, _ in self.keys:
            course_key_counts[course] += 1
        missing = [course for course, count in course_key_counts.items() if count == 0]
        if missing:
            raise ValueError(f"No feasible assignments for course(s): {missing}")

        # Create dictionaries for time slot start and end times (in minutes)
        self.slot_start_minutes = {
            slot: time_to_minutes(start)
            for slot, start in zip(self.time_slots_df['Slot'], self.time_slots_df['Start'])
        }
        self.slot_end_minutes = {
            slot: time_to_minutes(end)
            for slot, end in zip(self.time_slots_df['Slot'], self.time_slots_df['End'])
        }
        self.slot_days = {
            slot: set(expand_days(days))
            for slot, days in zip(self.time_slots_df['Slot'], self.time_slots_df['Days'])
        }

        # Apply user-defined constraints
        if not self._constraints:
            print("Warning: No constraints added. Schedule may be invalid.")
            print("Consider adding: CourseAssignment(), InstructorNoOverlap(), RoomNoOverlap(), RoomCapacity()")
        else:
            total_constraints = 0
            for constraint in self._constraints:
                count = constraint.apply(self)
                print(f"  Applied: {constraint.name} ({count} constraints)")
                total_constraints += count
            print(f"Total: {total_constraints} constraints applied")

        return True

    def get_day_start_pairs(self) -> set:
        """Collect all unique (day, start_time) pairs from all time slots."""
        day_start_pairs = set()
        for slot in self.time_slots:
            start_minutes = self.slot_start_minutes[slot]
            for day in self.slot_days[slot]:
                day_start_pairs.add((day, start_minutes))
        return day_start_pairs

    def slot_overlaps(self, slot: str, day: str, start_minutes: int, buffer_minutes: int = 15) -> bool:
        """Check if a slot overlaps with a given day and start time."""
        if day not in self.slot_days[slot]:
            return False
        slot_start = self.slot_start_minutes[slot]
        slot_end = self.slot_end_minutes[slot]
        return slot_start <= start_minutes and slot_end > (start_minutes - buffer_minutes)

    def optimize_schedule(self):
        """Solve the instructor scheduling problem using integer linear programming."""
        # Set up problem
        if not self.setup_problem():
            return None

        # Solve the problem
        solver = PULP_CBC_CMD(
            msg=1 if self.solver_verbose else 0,
            timeLimit=self.objective_timeout
        )
        self.prob.solve(solver)

        # Check if the problem is solved
        status = LpStatus[self.prob.status]
        if status == 'Optimal':
            self._extract_schedule()
            return self.schedule
        elif status == 'Not Solved':
            # Timeout case - check if we have a feasible solution
            if any(self.x[k].varValue == 1 for k in self.keys):
                print("Timeout reached, using best solution found")
                self._extract_schedule()
                return self.schedule
            else:
                print("No solution found within timeout")
                self.schedule = None
                return None
        else:
            print(f"No solution found (status: {status})")
            self.schedule = None
            return None

    def print_violated_constraints(self):
        """Print the names of constraints that are not satisfied."""
        print("\nViolated constraints:")
        for name, constraint in self.prob.constraints.items():
            if not constraint.valid():
                print(f"  {name}")

    def _extract_schedule(self):
        """Extract schedule from solved problem into a DataFrame."""
        schedule_data = []
        for k in self.keys:
            if self.x[k].varValue == 1:
                course, room, t = k
                slot_info = self.time_slots_df[self.time_slots_df['Slot'] == t].iloc[0]
                course_info = self.courses_df[self.courses_df['Course'] == course].iloc[0]
                schedule_data.append({
                    'Course': course,
                    'Room': room,
                    'Slot': t,
                    'Days': slot_info['Days'],
                    'Start': slot_info['Start'],
                    'End': slot_info['End'],
                    'Instructor': course_info['Instructor'],
                    'Enrollment': course_info['Enrollment'],
                    'Note': course_info.get('Note', '')
                })
        self.schedule = pd.DataFrame(schedule_data)

    def lexicographic_optimize(self, objectives: List[ObjectiveBase]):
        """
        Perform lexicographic optimization with ordered objectives.

        Optimizes objectives in priority order, with each objective's optimal
        value becoming a constraint for subsequent objectives.

        Args:
            objectives: Ordered list of ObjectiveBase instances to optimize

        Returns:
            DataFrame with optimized schedule, or None if no solution found

        Example:
            objectives = [
                MinimizeClassesBefore("9:00", instructor="Nelson"),
                MaximizePreferredRooms(["BLDG 120", "BLDG 220"]),
                MinimizeTimeSlotSpread()
            ]
            scheduler.lexicographic_optimize(objectives)
        """
        # Set up problem
        if not self.setup_problem():
            return None

        if not objectives:
            print("Warning: No objectives specified, using constraint satisfaction only")
            solver = PULP_CBC_CMD(
                msg=1 if self.solver_verbose else 0,
                timeLimit=self.objective_timeout
            )
            self.prob.solve(solver)
            if LpStatus[self.prob.status] == 'Optimal':
                self._extract_schedule()
                return self.schedule
            else:
                print("No solution found")
                self.schedule = None
                return None

        print(f"\n=== Lexicographic Optimization: {len(objectives)} objectives ===\n")

        # Track best schedule from completed objectives
        best_schedule = None
        solved_any = False

        try:
            # Optimize each objective in order
            for i, objective in enumerate(objectives):
                print(f"[{i+1}/{len(objectives)}] Optimizing: {objective.name}")

                expr = objective.evaluate(self)

                # An expression with no decision variables cannot be improved --
                # typically a course filter that matched nothing because those
                # courses are ignored or not offered. Skip it: its value is fixed,
                # and handing PuLP an empty objective makes it attach a dummy
                # variable to the problem that corrupts every later model file.
                if len(expr) == 0:
                    print("  ⚠ Skipped: this objective does not depend on any "
                          "scheduled course\n")
                    continue

                # Set objective function
                if objective.sense == 'minimize':
                    self.prob.sense = LpMinimize
                else:
                    self.prob.sense = LpMaximize
                self.prob.setObjective(expr)

                # Use warmStart after the first solve to provide a feasible starting point
                solver = PULP_CBC_CMD(
                    msg=1 if self.solver_verbose else 0,
                    timeLimit=self.objective_timeout,
                    warmStart=solved_any
                )
                self.prob.solve(solver)
                solved_any = True

                # Check solution status
                status = LpStatus[self.prob.status]
                if status == 'Optimal':
                    pass  # Continue normally
                elif status == 'Not Solved':
                    # Timeout case - check if we have a feasible solution
                    if not any(self.x[k].varValue == 1 for k in self.keys):
                        print(f"  ✗ No solution found within timeout")
                        self.schedule = None
                        return None
                else:
                    print(f"  ✗ No solution found (status: {status})")
                    self.schedule = None
                    return None

                # Get optimal value
                optimal_value = value(self.prob.objective)
                if optimal_value is None:
                    optimal_value = 0.0
                if status == 'Optimal':
                    print(f"  ✓ Optimal value: {optimal_value:.2f}")
                else:
                    print(f"  ⏱ Timed out at value: {optimal_value:.2f}")
                    print(f"  ⚠ WARNING: Skipping constraint (timeout solution may not be feasible)")

                # Extract and save intermediate schedule after each objective
                self._extract_schedule()
                best_schedule = self.schedule.copy()

                # Add constraint to lock this objective (with tolerance)
                # Don't constrain the last objective
                # Skip constraint if we timed out - CBC may report LP bound, not feasible solution
                if i < len(objectives) - 1 and status == 'Optimal':
                    tolerance = objective.tolerance
                    if objective.sense == 'minimize':
                        bound = optimal_value * (1 + tolerance)
                        self.prob += (
                            expr <= bound,
                            f"lock_objective_{i}"
                        )
                        if tolerance > 0:
                            print(f"    Constraining: value ≤ {bound:.2f} (tolerance: {tolerance*100:.1f}%)")
                        else:
                            print(f"    Constraining: value ≤ {bound:.2f}")
                    else:  # maximize
                        bound = optimal_value * (1 - tolerance)
                        self.prob += (
                            expr >= bound,
                            f"lock_objective_{i}"
                        )
                        if tolerance > 0:
                            print(f"    Constraining: value ≥ {bound:.2f} (tolerance: {tolerance*100:.1f}%)")
                        else:
                            print(f"    Constraining: value ≥ {bound:.2f}")
                print()

        except KeyboardInterrupt:
            print("\n\n⚠ Optimization interrupted by user")
            if best_schedule is not None:
                print("Returning best schedule from completed objectives")
                self.schedule = best_schedule
                return self.schedule
            else:
                print("No complete schedule available yet")
                return None

        if not solved_any:
            # Every objective was vacuous, so nothing has been solved yet; fall back
            # to finding any feasible schedule.
            print("No objective depends on the schedule; solving for feasibility only")
            solver = PULP_CBC_CMD(
                msg=1 if self.solver_verbose else 0,
                timeLimit=self.objective_timeout
            )
            self.prob.solve(solver)
            status = LpStatus[self.prob.status]
            if status != 'Optimal' and not any(self.x[k].varValue == 1 for k in self.keys):
                print(f"  ✗ No solution found (status: {status})")
                self.schedule = None
                return None

        # Extract final schedule
        self._extract_schedule()
        print("=== Optimization complete ===\n")
        return self.schedule

    def print_objective_values(self, objectives: list, filename: str = None) -> dict:
        """
        Print the current values of the given objectives based on the current solution.

        Args:
            objectives: List of objective instances to evaluate
            filename: Optional CSV filename to save the results

        Returns:
            Dictionary mapping objective names to their current values
        """
        from pulp import value

        results = {}

        # First pass: compute values and find max name length
        rows = []
        for objective in objectives:
            expr = objective.evaluate(self)
            val = value(expr)
            results[objective.name] = val
            sense = "min" if objective.sense == 'minimize' else "max"
            rows.append((objective.name, val, sense))

        max_name_len = max(len(row[0]) for row in rows) if rows else 20

        # Print table
        print("\nObjective Values:")
        print("-" * (max_name_len + 18))
        print("%-*s  %10s  %s" % (max_name_len, "Objective", "Value", "Sense"))
        print("-" * (max_name_len + 18))

        for name, val, sense in rows:
            print("%-*s  %10.2f  (%s)" % (max_name_len, name, val, sense))

        print("-" * (max_name_len + 18))

        # Save to CSV if filename provided
        if filename:
            import os
            dirname = os.path.dirname(filename)
            if dirname:
                os.makedirs(dirname, exist_ok=True)
            with open(filename, 'w') as f:
                f.write("Objective,Value,Sense\n")
                for name, val, sense in rows:
                    f.write(f'"{name}",{val},{sense}\n')
            print(f"Objective values saved to {filename}")

        return results

    def display_schedule(self):
        """Display the optimized schedule."""
        if self.schedule is not None:
            print("\nOptimized Schedule:")
            print(self.schedule)
        else:
            print("No schedule available. Please run optimize_schedule() first.")

    def save_schedule(self, filename: str = 'schedule.csv'):
        """Save the optimized schedule to a CSV file, sorted by course name."""
        if self.schedule is not None:
            import os
            dirname = os.path.dirname(filename)
            if dirname:
                os.makedirs(dirname, exist_ok=True)
            self.schedule.sort_values('Course').to_csv(filename, index=False)
            print(f"Schedule saved to {filename}")
        else:
            print("No schedule available to save. Please run optimize_schedule() first.")

    def visualize_schedule(self, output_file='schedule_visual.png', merge_rows=None, room_order=None, highlight_changes_from=None, highlight_time_changes_from=None):
        """
        Visualize the optimized schedule.

        Creates a visual representation of the schedule showing courses
        arranged by time and day. Delegates to visualize_schedule module
        for the actual visualization logic.

        Args:
            output_file: Path to save the visualization PNG (default: 'schedule_visual.png')
            merge_rows: Controls row merging behavior:
                - None or False: No merging, one row per room (default)
                - True: Merge all non-overlapping rooms
                - List of room names: Only merge the specified rooms if they don't overlap
                Room names are shown inside course blocks only for rooms that are
                actually merged with another room.
            room_order: Controls room display order (top to bottom on the plot):
                - None: Sort by capacity (largest at top, default)
                - List of room names: Display in the specified order (first = top)
            highlight_changes_from: Optional previous schedule to compare against:
                - None: No highlighting
                - str: Path to a CSV file with the previous schedule
                - DataFrame: Previous schedule DataFrame
                Courses that changed room or time slot will be highlighted with an orange border.
            highlight_time_changes_from: Optional previous schedule to compare against:
                - None: No highlighting
                - str: Path to a CSV file with the previous schedule
                - DataFrame: Previous schedule DataFrame
                Only courses that changed time slot (ignoring room) will be highlighted with an orange border.
        """
        if self.schedule is not None:
            visualize_schedule(self.schedule, self.rooms_df, output_file, merge_rows=merge_rows, room_order=room_order, highlight_changes_from=highlight_changes_from, highlight_time_changes_from=highlight_time_changes_from)
        else:
            print("No schedule available to visualize. Please run optimize_schedule() or lexicographic_optimize() first.")

def main():
    scheduler = InstructorScheduler()

    # Load data
    print("Loading room, course, and time slot data...")
    rooms = scheduler.load_rooms()
    courses = scheduler.load_courses()
    time_slots = scheduler.load_time_slots()

    if rooms is not None and courses is not None and time_slots is not None:
        print("\nRoom data preview:")
        print(rooms.head())
        print("\nCourse data preview:")
        print(courses.head())
        print("\nTime slot data preview:")
        print(time_slots.head())

        # Optimize schedule
        scheduler.optimize_schedule()
        scheduler.display_schedule()
        scheduler.save_schedule()

        # Create visualization
        if scheduler.schedule is not None:
            visualize_schedule(scheduler.schedule, rooms)
    else:
        print("Failed to load required data files")


if __name__ == "__main__":
    main()
