# satisfaculty

A python course scheduling optimization tool using integer linear programming.

## Installation

```bash
pip install satisfaculty
```

## Quick Start

```python
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
])

objectives = [MinimizeClassesBefore("9:00")]
scheduler.lexicographic_optimize(objectives)
scheduler.visualize_schedule()
```

This will output a complete schedule:

![Example schedule output](schedule_visual.png)

## Example

Example data files and a script are available in the [`example/`](https://github.com/zsunberg/satisfaculty/tree/main/example) directory of the repository.

## Contents

```{toctree}
:maxdepth: 2

formulation
objectives_guide
```
