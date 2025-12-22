# Satisfaculty

A course scheduling optimization tool using integer linear programming.

## Installation

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

## Usage

```python
from satisfaculty import InstructorScheduler, MinimizeClassesBefore

scheduler = InstructorScheduler()
scheduler.load_rooms()
scheduler.load_courses()
scheduler.load_time_slots()

objectives = [MinimizeClassesBefore("9:00")]
scheduler.lexicographic_optimize(objectives)
scheduler.visualize_schedule()
```

## Documentation

- [Objectives Guide](docs/OBJECTIVES_GUIDE.md)
