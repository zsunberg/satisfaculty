#!/usr/bin/env python3
"""
Example script demonstrating lexicographic optimization.

This shows how to define custom objective priorities for schedule optimization.
Each user can create their own script with different objective orderings.
"""

from satisfaculty import (
    InstructorScheduler,
    MinimizeClassesBefore,
    MinimizeClassesAfter,
    MaximizePreferredRooms,
)

scheduler = InstructorScheduler()
scheduler.load_rooms()
scheduler.load_courses()
scheduler.load_time_slots()

objectives = [
    MinimizeClassesBefore("9:00"),
]

scheduler.lexicographic_optimize(objectives)

scheduler.visualize_schedule()
