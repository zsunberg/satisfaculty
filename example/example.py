#!/usr/bin/env python3
"""
Example script demonstrating lexicographic optimization with configurable constraints.

This shows how to define custom constraints and objective priorities for schedule optimization.
Each user can create their own script with different constraint and objective configurations.
"""

from satisfaculty import *

scheduler = InstructorScheduler()
scheduler.load_rooms('rooms.csv')
scheduler.load_courses('courses.csv')
scheduler.load_time_slots('time_slots.csv')

# Add constraints (required for a valid schedule)
scheduler.add_constraints([
    AssignAllCourses(),
    NoInstructorOverlap(),
    NoRoomOverlap(),
    RoomCapacity(),
    ForceRooms(),
    ForceTimeSlots(),
])

# Define lexicographic optimization objectives (in priority order)
objectives = [
    MinimizeClassesBefore('9:00'),
]

scheduler.lexicographic_optimize(objectives)
scheduler.save_schedule('schedule.csv')
scheduler.visualize_schedule('schedule_visual.png')
