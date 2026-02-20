"""Satisfaculty - A course scheduling optimization tool."""

from .scheduler import InstructorScheduler
from .objectives import (
    MinimizeClassesBefore,
    MinimizeClassesAfter,
    MinimizeMinutesAfter,
    MaximizePreferredRooms,
    MinimizePreferredRooms,
    MaximizeBackToBackCourses,
)
from .constraints import (
    AssignAllCourses,
    NoInstructorOverlap,
    NoRoomOverlap,
    NoCourseOverlap,
    SameTimeSlot,
    RoomCapacity,
    AvoidRoomsForCourseType,
    ForceRooms,
    ForceTimeSlots,
)
from .visualize_schedule import visualize_schedule

__all__ = [
    "InstructorScheduler",
    # Objectives
    "MinimizeClassesBefore",
    "MinimizeClassesAfter",
    "MinimizeMinutesAfter",
    "MaximizePreferredRooms",
    "MinimizePreferredRooms",
    "MaximizeBackToBackCourses",
    # Constraints
    "AssignAllCourses",
    "NoInstructorOverlap",
    "NoRoomOverlap",
    "NoCourseOverlap",
    "SameTimeSlot",
    "RoomCapacity",
    "AvoidRoomsForCourseType",
    "ForceRooms",
    "ForceTimeSlots",
    # Utilities
    "visualize_schedule",
]
