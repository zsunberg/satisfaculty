#!/usr/bin/env python3
"""
Base class for lexicographic optimization objectives.

Objectives are optimized in order of priority, with each objective's
optimal value becoming a constraint for subsequent objectives.
"""

from abc import ABC, abstractmethod
from pulp import LpAffineExpression
from typing import Literal


class ObjectiveBase(ABC):
    """
    Abstract base class for optimization objectives.

    Each objective has:
    - A name for logging/debugging
    - A sense (minimize or maximize)
    - A tolerance for lexicographic constraints (allows some slack)
    - An evaluate() method that returns a PuLP expression
    """

    def __init__(
        self,
        name: str,
        sense: Literal['minimize', 'maximize'] = 'minimize',
        tolerance: float = 0.0
    ):
        """
        Initialize an optimization objective.

        Args:
            name: Human-readable name for this objective
            sense: 'minimize' or 'maximize'
            tolerance: Fractional tolerance when constraining this objective
                      (0.0 = exact, 0.05 = allow 5% deviation)
                      Only used when this becomes a constraint for later objectives
        """
        self.name = name
        self.sense = sense
        self.tolerance = tolerance

        if sense not in ['minimize', 'maximize']:
            raise ValueError(f"sense must be 'minimize' or 'maximize', got '{sense}'")

        if tolerance < 0:
            raise ValueError(f"tolerance must be non-negative, got {tolerance}")

    @abstractmethod
    def evaluate(self, scheduler) -> LpAffineExpression:
        """
        Evaluate this objective for the given scheduler.

        Args:
            scheduler: InstructorScheduler instance with problem setup
                      Has access to:
                      - scheduler.x: decision variables dict
                      - scheduler.keys: set of (course, room, time_slot) tuples
                      - scheduler.courses_df, rooms_df, time_slots_df: input data
                      - scheduler.enrollments, capacities, etc.: derived dicts

        Returns:
            PuLP expression to optimize (minimize or maximize based on self.sense)
        """
        pass

    def __repr__(self):
        return f"{self.__class__.__name__}(name='{self.name}', sense='{self.sense}', tolerance={self.tolerance})"
