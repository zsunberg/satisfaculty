# Lexicographic Optimization Guide

This guide explains how to use the flexible objective system for schedule optimization.

## Overview

The lexicographic optimization system allows you to define **ordered objectives** that are optimized in priority order:

1. The **first objective** is optimized to find its best possible value
2. That optimal value becomes a **constraint** for all subsequent objectives
3. The **second objective** is optimized within that constraint
4. This continues for all objectives in order

This ensures higher-priority objectives are always satisfied optimally before considering lower-priority ones.

## Quick Start

```python
from scheduler import InstructorScheduler
from objectives import MinimizeClassesBefore, MaximizePreferredRooms

# Load data
scheduler = InstructorScheduler()
scheduler.load_rooms()
scheduler.load_courses()
scheduler.load_time_slots()

# Define objectives in priority order
objectives = [
    MinimizeClassesBefore("9:00", instructor="Neogi"),
    MaximizePreferredRooms(["AERO 120", "AERO 220"])
]

# Optimize
schedule = scheduler.lexicographic_optimize(objectives)
```

## Creating Custom Scripts

Each user can create their own script with different objectives:

1. Copy `example_lexicographic.py` to a new file (e.g., `my_schedule.py`)
2. Modify the `objectives` list to match your priorities
3. Run your custom script

**Example custom script:**

```python
#!/usr/bin/env python3
import sys
sys.path.append('src')

from scheduler import InstructorScheduler
from objectives import *

scheduler = InstructorScheduler()
scheduler.load_rooms()
scheduler.load_courses()
scheduler.load_time_slots()

# YOUR custom objectives here
objectives = [
    MinimizeClassesAfter("15:00"),  # Avoid late classes
    PreferTimeSlots(["MWF 10:00-10:50"]),  # Prefer specific times
]

scheduler.lexicographic_optimize(objectives)
scheduler.save_schedule('output/my_schedule.csv')
```

## Available Objectives

### Time-Based Objectives

#### `MinimizeClassesBefore(time, instructor=None, course_type=None)`
Minimize classes scheduled before a given time.

```python
# Avoid early classes for everyone
MinimizeClassesBefore("9:00")

# Specific instructor
MinimizeClassesBefore("9:00", instructor="Neogi")

# Specific course type
MinimizeClassesBefore("9:00", course_type="Lab")
```

#### `MinimizeClassesAfter(time, instructor=None, course_type=None)`
Minimize classes scheduled after a given time.

```python
# Avoid late afternoon classes
MinimizeClassesAfter("16:00")

# For specific instructor
MinimizeClassesAfter("17:00", instructor="Smith")
```

#### `PreferTimeSlots(preferred_slots, instructor=None, course_type=None)`
Maximize assignments to specific time slots.

```python
# Prefer MWF mornings
PreferTimeSlots(["MWF 10:00-10:50", "MWF 11:00-11:50"])

# For specific instructor
PreferTimeSlots(["TTH 14:00-15:15"], instructor="Neogi")
```

### Room-Based Objectives

#### `MaximizePreferredRooms(preferred_rooms, instructor=None, course_type=None)`
Maximize use of preferred rooms.

```python
# Prefer specific rooms
MaximizePreferredRooms(["AERO 120", "AERO 220"])

# Only for lectures
MaximizePreferredRooms(["AERO 120"], course_type="Lecture")

# For specific instructor
MaximizePreferredRooms(["AERO 120"], instructor="Neogi")
```

#### `MinimizeRoomChanges(instructor=None)`
Minimize number of different rooms each instructor uses.

```python
# For all instructors
MinimizeRoomChanges()

# Specific instructor
MinimizeRoomChanges(instructor="Neogi")
```

#### `MinimizeTotalEnrollmentInRooms(rooms, sense='minimize')`
Control enrollment distribution across rooms.

```python
# Avoid putting large classes in certain rooms
MinimizeTotalEnrollmentInRooms(["Small Room A", "Small Room B"])

# Prefer certain rooms for large classes (use maximize)
MinimizeTotalEnrollmentInRooms(["Large Hall"], sense='maximize')
```

### Efficiency Objectives

#### `MinimizeTimeSlotSpread()`
Minimize the total number of distinct time slots used.

```python
# Consolidate schedule
MinimizeTimeSlotSpread()
```

## Parameters

### Common Parameters

All objectives support these parameters:

- **`tolerance`** (float, default 0.0): Fractional tolerance when this objective becomes a constraint
  - `0.0` = exact (no flexibility)
  - `0.05` = allow 5% deviation
  - `0.10` = allow 10% deviation

- **`sense`** (str): Direction of optimization
  - `'minimize'` = minimize the objective value
  - `'maximize'` = maximize the objective value

### Using Tolerance

Tolerance allows flexibility for lower-priority objectives:

```python
objectives = [
    # Must be exactly optimal (no tolerance)
    MinimizeClassesBefore("9:00", instructor="Neogi", tolerance=0.0),

    # Can be up to 10% suboptimal if it helps later objectives
    MaximizePreferredRooms(["AERO 120"], tolerance=0.10),

    # Can be up to 20% suboptimal
    MinimizeRoomChanges(tolerance=0.20),
]
```

## Creating Custom Objectives

To create your own objective, inherit from `ObjectiveBase`:

```python
from objective_base import ObjectiveBase
from pulp import lpSum
from scheduler import filter_keys

class MyCustomObjective(ObjectiveBase):
    def __init__(self, my_param, tolerance=0.0):
        self.my_param = my_param
        super().__init__(
            name=f"My custom objective with {my_param}",
            sense='minimize',
            tolerance=tolerance
        )

    def evaluate(self, scheduler):
        # Return a PuLP expression to optimize
        # You have access to:
        # - scheduler.x: decision variables
        # - scheduler.keys: set of (course, room, time_slot) tuples
        # - scheduler.courses_df, rooms_df, time_slots_df
        # - scheduler.enrollments, capacities, etc.

        # Example: count assignments matching some criteria
        def my_filter(course, room, time_slot):
            # Your custom logic here
            return some_condition

        filtered = filter_keys(scheduler.keys, predicate=my_filter)
        return lpSum(scheduler.x[k] for k in filtered)
```

Then use it in your script:

```python
objectives = [
    MyCustomObjective(my_param="value"),
    # ... other objectives
]
```

## Tips

1. **Order matters!** Put your most important objectives first
2. **Start simple**: Begin with 1-2 objectives, then add more
3. **Use tolerance**: Allow some flexibility for lower-priority objectives
4. **Test incrementally**: Add objectives one at a time to see their impact
5. **Check feasibility**: Too many strict constraints may make the problem infeasible

## Output

The lexicographic optimizer prints detailed progress:

```
=== Lexicographic Optimization: 3 objectives ===

[1/3] Optimizing: Minimize classes before 9:00 for Neogi
  ✓ Optimal value: 0.00
    Constraining: value ≤ 0.00

[2/3] Optimizing: Maximize preferred rooms (AERO 120, AERO 220) (Lecture)
  ✓ Optimal value: 5.00
    Constraining: value ≥ 4.50 (tolerance: 10.0%)

[3/3] Optimizing: Minimize distinct time slots used
  ✓ Optimal value: 8.00

=== Optimization complete ===
```

This shows:
- What objective is being optimized
- Its optimal value
- What constraint is added for subsequent objectives
- Whether tolerance is applied

## Examples

See `example_lexicographic.py` for complete working examples with different objective combinations.
