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
        filter_keys(keys, course='ASEN-2402-001')

        # Match all courses/times for a specific room
        filter_keys(keys, room='AERO 120')

        # Match specific course and room, all time slots
        filter_keys(keys, course='ASEN-2402-001', room='AERO 120')

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
    def __init__(self):
        self.time_slots_df = None
        
    def load_rooms(self, filename: str = 'data/rooms.csv'):
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
    
    def load_courses(self, filename: str = 'data/courses.csv'):
        """Load course data from CSV file."""
        try:
            self.courses_df = pd.read_csv(filename)
            
            # Check for duplicate courses
            courses = self.courses_df['Course']
            if len(courses) != len(courses.unique()):
                duplicates = courses[courses.duplicated()].unique()
                raise ValueError(f"Duplicate courses found: {list(duplicates)}")
            
            print(f"Loaded {len(self.courses_df)} courses from {filename}")
            return self.courses_df
        except FileNotFoundError:
            print(f"Error: {filename} not found")
            return None
        except Exception as e:
            print(f"Error loading courses: {e}")
            return None

    def load_time_slots(self, filename: str = 'data/time_slots.csv'):
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

    def make_overlap_predicate(self, time_slot: str, room: str | object = ALL, buffer_minutes: int = 15) -> Callable[[str, str, str], bool]:
        """
        Create a predicate that returns True if a key overlaps with the given time slot.

        Args:
            time_slot: The reference time slot to check overlaps against
            room: Room to match, or ALL to match all rooms
            buffer_minutes: Minutes before slot start to still count as overlap (default 15)
        """
        t_start = self.slot_start_minutes[time_slot]
        t_days = self.slot_days[time_slot]

        def predicate(course: str, r: str, slot: str) -> bool:
            if room is not ALL and r != room:
                return False
            # Check if days overlap
            if not self.slot_days[slot] & t_days:
                return False
            # Check time overlap
            slot_start = self.slot_start_minutes[slot]
            slot_end = self.slot_end_minutes[slot]
            return slot_start <= t_start and slot_end > (t_start - buffer_minutes)

        return predicate

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

        # Create the constraint satisfaction problem
        self.prob = LpProblem("Instructor_Scheduling", LpMinimize)

        # Extract input parameters (store as instance variables for objectives)
        self.courses = list(self.courses_df['Course'])
        self.rooms = list(self.rooms_df['Room'])
        self.time_slots = list(self.time_slots_df['Slot'])
        self.instructors = list(self.courses_df['Instructor'].unique())

        # Create dictionaries for enrollments and capacities
        self.enrollments = dict(zip(self.courses_df['Course'], self.courses_df['Enrollment']))
        self.capacities = dict(zip(self.rooms_df['Room'], self.rooms_df['Capacity']))

        # Create dictionaries for course and time slot types
        self.course_types = dict(zip(self.courses_df['Course'], self.courses_df['Type']))
        self.slot_types = dict(zip(self.time_slots_df['Slot'], self.time_slots_df['Type']))

        # Create matrix a; a[(instructor, course)] = 1 if instructor teaches course
        self.a = {}
        for instructor in self.instructors:
            for course in self.courses:
                if instructor in self.courses_df[self.courses_df['Course'] == course]['Instructor'].values:
                    self.a[(instructor, course)] = 1
                else:
                    self.a[(instructor, course)] = 0

        # Create binary decision variables using LpVariable.dicts
        # x[(course, room, time)] = 1 if course is assigned to room at time slot
        # Only create variables where course type matches time slot type
        self.keys = set([
            (course, room, t)
            for course in self.courses
            for room in self.rooms
            for t in self.time_slots
            if self.course_types[course] == self.slot_types[t]
        ])
        self.x = LpVariable.dicts("x", list(self.keys), cat='Binary')

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

        # Course must be taught once
        for course in self.courses:
            self.prob += lpSum(self.x[k] for k in filter_keys(self.keys, course=course)) == 1

        # Instructor can only be teaching one course at a time
        for instructor in self.instructors:
            for t in self.time_slots:
                self.prob += lpSum(
                    self.x[k] * self.a[(instructor, k[0])]
                    for k in filter_keys(self.keys, predicate=self.make_overlap_predicate(t))
                ) <= 1

        # Room can only have one course at a time (checking for overlaps)
        for room in self.rooms:
            for t in self.time_slots:
                self.prob += lpSum(
                    self.x[k] for k in filter_keys(self.keys, predicate=self.make_overlap_predicate(t, room=room))
                ) <= 1

        # Room capacity constraints
        for room in self.rooms:
            for t in self.time_slots:
                self.prob += lpSum(
                    self.x[k] * self.enrollments[k[0]]
                    for k in filter_keys(self.keys, room=room, time_slot=t)
                ) <= self.capacities[room]

        return True

    def optimize_schedule(self):
        """Solve the instructor scheduling problem using integer linear programming."""
        # Set up problem
        if not self.setup_problem():
            return None

        # Solve the problem (msg=0 silences solver output)
        solver = PULP_CBC_CMD(msg=0)
        self.prob.solve(solver)

        # Check if the problem is solved
        if LpStatus[self.prob.status] != 'Optimal':
            print("No solution found")
            self.schedule = None
            return

        # Extract schedule from solution
        self._extract_schedule()
        return self.schedule

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
                    'Days': slot_info['Days'],
                    'Start': slot_info['Start'],
                    'End': slot_info['End'],
                    'Instructor': course_info['Instructor'],
                    'Enrollment': course_info['Enrollment']
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
                MinimizeClassesBefore("9:00", instructor="Neogi"),
                MaximizePreferredRooms(["AERO 120", "AERO 220"]),
                MinimizeTimeSlotSpread()
            ]
            scheduler.lexicographic_optimize(objectives)
        """
        # Set up problem
        if not self.setup_problem():
            return None

        if not objectives:
            print("Warning: No objectives specified, using constraint satisfaction only")
            solver = PULP_CBC_CMD(msg=0)
            self.prob.solve(solver)
            if LpStatus[self.prob.status] == 'Optimal':
                self._extract_schedule()
                return self.schedule
            else:
                print("No solution found")
                self.schedule = None
                return None

        print(f"\n=== Lexicographic Optimization: {len(objectives)} objectives ===\n")

        # Create silent solver
        solver = PULP_CBC_CMD(msg=0)

        # Optimize each objective in order
        for i, objective in enumerate(objectives):
            print(f"[{i+1}/{len(objectives)}] Optimizing: {objective.name}")

            # Set objective function
            if objective.sense == 'minimize':
                self.prob.sense = LpMinimize
                self.prob.setObjective(objective.evaluate(self))
            else:
                self.prob.sense = LpMaximize
                self.prob.setObjective(objective.evaluate(self))

            # Solve (msg=0 silences solver output)
            self.prob.solve(solver)

            # Check solution status
            status = LpStatus[self.prob.status]
            if status != 'Optimal':
                print(f"  ✗ No solution found (status: {status})")
                self.schedule = None
                return None

            # Get optimal value
            optimal_value = value(self.prob.objective)
            print(f"  ✓ Optimal value: {optimal_value:.2f}")

            # Add constraint to lock this objective (with tolerance)
            # Don't constrain the last objective
            if i < len(objectives) - 1:
                tolerance = objective.tolerance
                if objective.sense == 'minimize':
                    bound = optimal_value * (1 + tolerance)
                    self.prob += (
                        objective.evaluate(self) <= bound,
                        f"lock_objective_{i}"
                    )
                    if tolerance > 0:
                        print(f"    Constraining: value ≤ {bound:.2f} (tolerance: {tolerance*100:.1f}%)")
                    else:
                        print(f"    Constraining: value ≤ {bound:.2f}")
                else:  # maximize
                    bound = optimal_value * (1 - tolerance)
                    self.prob += (
                        objective.evaluate(self) >= bound,
                        f"lock_objective_{i}"
                    )
                    if tolerance > 0:
                        print(f"    Constraining: value ≥ {bound:.2f} (tolerance: {tolerance*100:.1f}%)")
                    else:
                        print(f"    Constraining: value ≥ {bound:.2f}")
            print()

        # Extract final schedule
        self._extract_schedule()
        print("=== Optimization complete ===\n")
        return self.schedule

    def display_schedule(self):
        """Display the optimized schedule."""
        if self.schedule is not None:
            print("\nOptimized Schedule:")
            print(self.schedule)
        else:
            print("No schedule available. Please run optimize_schedule() first.")

    def save_schedule(self, filename: str = 'output/schedule.csv'):
        """Save the optimized schedule to a CSV file."""
        if self.schedule is not None:
            self.schedule.to_csv(filename, index=False)
            print(f"Schedule saved to {filename}")
        else:
            print("No schedule available to save. Please run optimize_schedule() first.")

    def visualize_schedule(self):
        """
        Visualize the optimized schedule.

        Creates a visual representation of the schedule showing courses
        arranged by time and day. Delegates to visualize_schedule module
        for the actual visualization logic.
        """
        if self.schedule is not None:
            visualize_schedule(self.schedule, self.rooms_df)
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
