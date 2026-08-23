#!/usr/bin/env python3
"""
Tests for skipping (and warning about) courses that constraints and objectives
name but that are not being scheduled -- either ignored or not offered at all.
"""

import contextlib
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from satisfaculty import (
    InstructorScheduler,
    AssignAllCourses,
    NoRoomOverlap,
    NoCourseOverlap,
    SameTimeSlot,
    MaximizeBackToBackCourses,
    MinimizeClassesAfter,
    MinimizeClassesBefore,
)


@contextlib.contextmanager
def scheduler_with(course_rows, slot_rows=None):
    """Build a loaded scheduler from inline course rows; yields (scheduler, output)."""
    slot_rows = slot_rows or [
        'Slot1,MWF,8:00,9:00,Lecture',
        'Slot2,MWF,9:00,10:00,Lecture',
        'Slot3,MWF,10:00,11:00,Lecture',
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        rooms_file = os.path.join(tmpdir, 'rooms.csv')
        with open(rooms_file, 'w') as f:
            f.write('Room,Capacity,Room Type\n')
            f.write('Room1,100,Lecture\n')
            f.write('Room2,100,Lecture\n')

        courses_file = os.path.join(tmpdir, 'courses.csv')
        with open(courses_file, 'w') as f:
            f.write('Course,Instructor,Enrollment,Slot Type,Room Type,Ignore\n')
            for row in course_rows:
                f.write(row + '\n')

        slots_file = os.path.join(tmpdir, 'time_slots.csv')
        with open(slots_file, 'w') as f:
            f.write('Slot,Days,Start,End,Slot Type\n')
            for row in slot_rows:
                f.write(row + '\n')

        scheduler = InstructorScheduler()
        scheduler.load_rooms(rooms_file)
        scheduler.load_courses(courses_file)
        scheduler.load_time_slots(slots_file)
        yield scheduler


# Course1 is scheduled, Course2 is ignored, Course3 is never mentioned in a test's
# constraints unless it wants a second live course.
DEFAULT_COURSES = [
    'Course1,Smith,50,Lecture,Lecture,',
    'Course2,Smith,50,Lecture,Lecture,TRUE',
    'Course3,Jones,50,Lecture,Lecture,',
]


def solve_capturing(scheduler, objectives=None):
    """Run the solve, returning (schedule, captured stdout)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        if objectives is None:
            schedule = scheduler.optimize_schedule()
        else:
            schedule = scheduler.lexicographic_optimize(objectives)
    return schedule, buf.getvalue()


def test_load_courses_names_the_ignored_courses():
    """The ignored courses are named, not just counted, so a log shows which."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        with scheduler_with(DEFAULT_COURSES):
            pass
    output = buf.getvalue()
    assert 'Ignored 1 course(s)' in output, output
    assert 'Course2' in output, output

    print('✓ test_load_courses_names_the_ignored_courses passed')


def test_no_course_overlap_skips_missing_courses():
    """An ignored and a never-listed course are dropped, each with a warning."""
    with scheduler_with(DEFAULT_COURSES) as scheduler:
        scheduler.add_constraints([
            AssignAllCourses(),
            NoRoomOverlap(),
            NoCourseOverlap(['Course1', 'Course2', 'Course3', 'NoSuchCourse']),
        ])
        schedule, output = solve_capturing(scheduler)

    assert schedule is not None, 'Expected a schedule, got none'
    assert len(schedule) == 2, f'Expected 2 scheduled courses, got {len(schedule)}'
    assert "'Course2'" in output, output
    assert "'NoSuchCourse'" in output, output
    # The constraint still binds the two courses that are being scheduled.
    assert schedule.iloc[0]['Slot'] != schedule.iloc[1]['Slot']

    print('✓ test_no_course_overlap_skips_missing_courses passed')


def test_same_time_slot_skips_missing_courses():
    """SameTimeSlot used to raise on a missing course; now it warns and skips it."""
    with scheduler_with(DEFAULT_COURSES) as scheduler:
        scheduler.add_constraints([
            AssignAllCourses(),
            NoRoomOverlap(),
            SameTimeSlot(['Course1', 'Course2', 'Course3']),
        ])
        schedule, output = solve_capturing(scheduler)

    assert schedule is not None, 'Expected a schedule, got none'
    assert "'Course2'" in output, output
    # Course1 and Course3 remain, so they must still share a slot.
    slots = set(schedule['Slot'])
    assert len(slots) == 1, f'Expected both courses in one slot, got {slots}'

    print('✓ test_same_time_slot_skips_missing_courses passed')


def test_same_time_slot_dropped_when_too_few_courses_remain():
    """With fewer than two courses left there is nothing to tie together."""
    with scheduler_with(DEFAULT_COURSES) as scheduler:
        scheduler.add_constraints([
            AssignAllCourses(),
            NoRoomOverlap(),
            SameTimeSlot(['Course1', 'Course2']),
        ])
        schedule, output = solve_capturing(scheduler)

    assert schedule is not None, 'Expected a schedule, got none'
    assert 'fewer than two courses' in output, output

    print('✓ test_same_time_slot_dropped_when_too_few_courses_remain passed')


def test_back_to_back_objective_skips_missing_courses():
    """MaximizeBackToBackCourses used to raise on a missing course."""
    with scheduler_with(DEFAULT_COURSES) as scheduler:
        scheduler.add_constraints([AssignAllCourses(), NoRoomOverlap()])
        schedule, output = solve_capturing(scheduler, [
            MaximizeBackToBackCourses(['Course1', 'Course2', 'Course3']),
        ])

    assert schedule is not None, 'Expected a schedule, got none'
    assert "'Course2'" in output, output

    print('✓ test_back_to_back_objective_skips_missing_courses passed')


def test_back_to_back_objective_with_no_courses_left():
    """All named courses missing: the objective goes constant, the solve completes."""
    with scheduler_with(DEFAULT_COURSES) as scheduler:
        scheduler.add_constraints([AssignAllCourses(), NoRoomOverlap()])
        schedule, output = solve_capturing(scheduler, [
            MaximizeBackToBackCourses(['Course2', 'NoSuchCourse']),
            MinimizeClassesAfter('9:00'),
        ])

    assert schedule is not None, 'Expected a schedule, got none'
    assert 'nothing to place back-to-back' in output, output

    print('✓ test_back_to_back_objective_with_no_courses_left passed')


def test_objective_course_filter_warns_once():
    """A course-filtered objective warns, and only once despite repeated evaluate()."""
    with scheduler_with(DEFAULT_COURSES) as scheduler:
        scheduler.add_constraints([AssignAllCourses(), NoRoomOverlap()])
        objectives = [
            MinimizeClassesAfter('9:00', courses=['Course1', 'Course2']),
            MinimizeClassesAfter('10:00'),
        ]
        schedule, output = solve_capturing(scheduler, objectives)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            scheduler.print_objective_values(objectives)
        output += buf.getvalue()

    assert schedule is not None, 'Expected a schedule, got none'
    assert output.count("'Course2'") == 1, (
        f"Expected exactly one warning about Course2, got {output.count(chr(39) + 'Course2' + chr(39))}"
    )

    print('✓ test_objective_course_filter_warns_once passed')


def test_vacuous_objective_does_not_break_later_solves():
    """
    An objective whose courses are all missing has no decision variables. Handing
    PuLP an empty objective attaches a dummy variable to the problem that corrupts
    every model file written afterwards, so such an objective must be skipped.
    The later objectives still have to solve.
    """
    with scheduler_with(DEFAULT_COURSES) as scheduler:
        scheduler.add_constraints([AssignAllCourses(), NoRoomOverlap()])
        schedule, output = solve_capturing(scheduler, [
            MinimizeClassesAfter('9:00', courses=['Course2']),
            MinimizeClassesAfter('9:00'),
            MinimizeClassesBefore('9:00'),
        ])

    assert schedule is not None, 'Expected a schedule, got none'
    assert len(schedule) == 2, f'Expected 2 scheduled courses, got {len(schedule)}'
    assert 'does not depend on any scheduled course' in output, output

    print('✓ test_vacuous_objective_does_not_break_later_solves passed')


def test_all_objectives_vacuous_still_produces_a_schedule():
    """With nothing left to optimize, fall back to a feasibility solve."""
    with scheduler_with(DEFAULT_COURSES) as scheduler:
        scheduler.add_constraints([AssignAllCourses(), NoRoomOverlap()])
        schedule, output = solve_capturing(scheduler, [
            MinimizeClassesAfter('9:00', courses=['Course2']),
        ])

    assert schedule is not None, 'Expected a schedule, got none'
    assert len(schedule) == 2, f'Expected 2 scheduled courses, got {len(schedule)}'
    assert 'feasibility only' in output, output

    print('✓ test_all_objectives_vacuous_still_produces_a_schedule passed')


def test_warn_missing_false_is_silent():
    """Carry-over lists that are only partly offered can opt out of the warnings."""
    with scheduler_with(DEFAULT_COURSES) as scheduler:
        scheduler.add_constraints([
            AssignAllCourses(),
            NoRoomOverlap(),
            NoCourseOverlap(['Course1', 'Course2'], warn_missing=False),
            SameTimeSlot(['Course1', 'Course2', 'Course3'], warn_missing=False),
        ])
        objectives = [
            MaximizeBackToBackCourses(['Course1', 'Course2'], warn_missing=False),
            MinimizeClassesAfter('9:00', courses=['Course1', 'Course2'], warn_missing=False),
        ]
        schedule, output = solve_capturing(scheduler, objectives)

    assert schedule is not None, 'Expected a schedule, got none'
    assert 'will be skipped' not in output, output
    assert 'fewer than two courses' not in output, output

    print('✓ test_warn_missing_false_is_silent passed')


def run_all_tests():
    """Run all tests."""
    print('Running missing-course warning tests...\n')

    test_load_courses_names_the_ignored_courses()
    test_no_course_overlap_skips_missing_courses()
    test_same_time_slot_skips_missing_courses()
    test_same_time_slot_dropped_when_too_few_courses_remain()
    test_back_to_back_objective_skips_missing_courses()
    test_back_to_back_objective_with_no_courses_left()
    test_objective_course_filter_warns_once()
    test_vacuous_objective_does_not_break_later_solves()
    test_all_objectives_vacuous_still_produces_a_schedule()
    test_warn_missing_false_is_silent()

    print('\n' + '=' * 50)
    print('All missing-course warning tests passed!')
    print('=' * 50)


if __name__ == '__main__':
    run_all_tests()
