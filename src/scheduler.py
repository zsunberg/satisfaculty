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
from visualize_schedule import visualize_schedule


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

    def optimize_schedule(self):
        """Solve the instructor scheduling problem using integer linear programming."""
        if self.rooms_df is None or self.courses_df is None:
            print("Error: Room and course data must be loaded first")
            return None

        if self.time_slots_df is None:
            print("Error: Time slot data must be loaded first")
            return None

        # Create the constraint satisfaction problem
        prob = LpProblem("Instructor_Scheduling", LpMinimize)

        # Extract input parameters
        courses = list(self.courses_df['Course'])
        rooms = list(self.rooms_df['Room'])
        time_slots = list(self.time_slots_df['Slot'])
        instructors = list(self.courses_df['Instructor'].unique())

        # Create dictionaries for enrollments and capacities
        enrollments = dict(zip(self.courses_df['Course'], self.courses_df['Enrollment']))
        capacities = dict(zip(self.rooms_df['Room'], self.rooms_df['Capacity']))

        # Create dictionaries for course and time slot types
        course_types = dict(zip(self.courses_df['Course'], self.courses_df['Type']))
        slot_types = dict(zip(self.time_slots_df['Slot'], self.time_slots_df['Type']))

        # Create matrix a; a[(instructor, course)] = 1 if instructor teaches course
        a = {}
        for instructor in instructors:
            for course in courses:
                if instructor in self.courses_df[self.courses_df['Course'] == course]['Instructor'].values:
                    a[(instructor, course)] = 1
                else:
                    a[(instructor, course)] = 0

        # Create binary decision variables using LpVariable.dicts
        # x[(course, room, time)] = 1 if course is assigned to room at time slot
        # Only create variables where course type matches time slot type
        keys = [(course, room, t) for course in courses for room in rooms for t in time_slots if course_types[course] == slot_types[t]]
        x = LpVariable.dicts("x", keys, cat='Binary')
        key_set = set(keys)  # Convert to set for filtering and iteration

        # Course must be taught once
        for course in courses:
            prob += lpSum(x[k] for k in filter_keys(key_set, course=course)) == 1

        # Instructor can only be teaching one course at a time
        for instructor in instructors:
            for t in time_slots:
                prob += lpSum(x[k] * a[(instructor, k[0])] for k in filter_keys(key_set, time_slot=t)) <= 1

        # Room can only have one course at a time
        for room in rooms:
            for t in time_slots:
                prob += lpSum(x[k] for k in filter_keys(key_set, room=room, time_slot=t)) <= 1

        # Room capacity constraints
        for room in rooms:
            for t in time_slots:
                prob += lpSum(x[k] * enrollments[k[0]] for k in filter_keys(key_set, room=room, time_slot=t)) <= capacities[room]

        # Solve the problem
        prob.solve()

        # Check if the problem is solved
        if LpStatus[prob.status] != 'Optimal':
            print("No solution found")
            self.schedule = None
            return

        # Create the schedule (dataframe with course, room, time slot)
        schedule_data = []
        for k in key_set:
            if x[k].varValue == 1:
                course, room, t = k
                slot_info = self.time_slots_df[self.time_slots_df['Slot'] == t].iloc[0]
                schedule_data.append({
                    'Course': course,
                    'Room': room,
                    'Days': slot_info['Days'],
                    'Start': slot_info['Start'],
                    'End': slot_info['End'],
                    'Instructor': self.courses_df[self.courses_df['Course'] == course]['Instructor'].values[0]
                })
        self.schedule = pd.DataFrame(schedule_data)

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
