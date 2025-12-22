"""Satisfaculty - A course scheduling optimization tool."""

from .scheduler import InstructorScheduler
from .objectives import (
    MinimizeClassesBefore,
    MinimizeClassesAfter,
    MaximizePreferredRooms,
)
from .visualize_schedule import visualize_schedule

__all__ = [
    "InstructorScheduler",
    "MinimizeClassesBefore",
    "MinimizeClassesAfter",
    "MaximizePreferredRooms",
    "visualize_schedule",
]
