#!/usr/bin/env python3
"""
Tests for the filter_keys function and InstructorScheduler.filter_schedule_keys method.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.scheduler import filter_keys, ALL, InstructorScheduler


def test_filter_by_course():
    """Test filtering by course name."""
    test_keys = [
        ('CS101', 'RoomA', 'MWF-0830'),
        ('CS101', 'RoomB', 'MWF-0830'),
        ('CS202', 'RoomA', 'TTH-1000'),
        ('CS202', 'RoomB', 'TTH-1000'),
    ]

    filtered = filter_keys(test_keys, course='CS101')
    assert len(filtered) == 2, f'Expected 2 results, got {len(filtered)}'
    assert all(c == 'CS101' for c, r, t in filtered), 'All results should have course CS101'
    print('✓ test_filter_by_course passed')


def test_filter_by_room():
    """Test filtering by room name."""
    test_keys = [
        ('CS101', 'RoomA', 'MWF-0830'),
        ('CS101', 'RoomB', 'MWF-0830'),
        ('CS202', 'RoomA', 'TTH-1000'),
        ('CS202', 'RoomB', 'TTH-1000'),
    ]

    filtered = filter_keys(test_keys, room='RoomA')
    assert len(filtered) == 2, f'Expected 2 results, got {len(filtered)}'
    assert all(r == 'RoomA' for c, r, t in filtered), 'All results should have room RoomA'
    print('✓ test_filter_by_room passed')


def test_filter_by_time_slot():
    """Test filtering by time slot."""
    test_keys = [
        ('CS101', 'RoomA', 'MWF-0830'),
        ('CS101', 'RoomB', 'MWF-0830'),
        ('CS202', 'RoomA', 'TTH-1000'),
        ('CS202', 'RoomB', 'TTH-1000'),
    ]

    filtered = filter_keys(test_keys, time_slot='MWF-0830')
    assert len(filtered) == 2, f'Expected 2 results, got {len(filtered)}'
    assert all(t == 'MWF-0830' for c, r, t in filtered), 'All results should have time MWF-0830'
    print('✓ test_filter_by_time_slot passed')


def test_filter_by_multiple_criteria():
    """Test filtering by multiple criteria."""
    test_keys = [
        ('CS101', 'RoomA', 'MWF-0830'),
        ('CS101', 'RoomB', 'MWF-0830'),
        ('CS202', 'RoomA', 'TTH-1000'),
        ('CS202', 'RoomB', 'TTH-1000'),
    ]

    filtered = filter_keys(test_keys, course='CS101', room='RoomA')
    assert len(filtered) == 1, f'Expected 1 result, got {len(filtered)}'
    assert filtered[0] == ('CS101', 'RoomA', 'MWF-0830'), f'Unexpected result: {filtered[0]}'
    print('✓ test_filter_by_multiple_criteria passed')


def test_filter_with_explicit_all():
    """Test filtering with explicit ALL sentinel."""
    test_keys = [
        ('CS101', 'RoomA', 'MWF-0830'),
        ('CS101', 'RoomB', 'MWF-0830'),
        ('CS202', 'RoomA', 'TTH-1000'),
        ('CS202', 'RoomB', 'TTH-1000'),
    ]

    filtered = filter_keys(test_keys, course=ALL, room=ALL, time_slot=ALL)
    assert len(filtered) == 4, f'Expected 4 results, got {len(filtered)}'
    print('✓ test_filter_with_explicit_all passed')


def test_filter_no_matches():
    """Test filtering with no matching results."""
    test_keys = [
        ('CS101', 'RoomA', 'MWF-0830'),
        ('CS101', 'RoomB', 'MWF-0830'),
    ]

    filtered = filter_keys(test_keys, course='CS999')
    assert len(filtered) == 0, f'Expected 0 results, got {len(filtered)}'
    print('✓ test_filter_no_matches passed')


def test_filter_with_predicate():
    """Test filtering with custom predicate function."""
    test_keys = [
        ('CS101', 'RoomA', 'MWF-0830'),
        ('CS101', 'RoomB', 'MWF-0830'),
        ('CS202', 'RoomA', 'TTH-1000'),
        ('MATH301', 'RoomB', 'TTH-1000'),
    ]

    # Filter for courses starting with 'CS'
    filtered = filter_keys(test_keys, predicate=lambda c, r, t: c.startswith('CS'))
    assert len(filtered) == 3, f'Expected 3 results, got {len(filtered)}'
    assert all(c.startswith('CS') for c, r, t in filtered), 'All results should start with CS'
    print('✓ test_filter_with_predicate passed')


def test_accepts_set_and_list():
    """Test that filter_keys accepts both set and list inputs."""
    test_keys_list = [
        ('CS101', 'RoomA', 'MWF-0830'),
        ('CS101', 'RoomB', 'MWF-0830'),
    ]
    test_keys_set = set(test_keys_list)

    filtered_from_list = filter_keys(test_keys_list, course='CS101')
    filtered_from_set = filter_keys(test_keys_set, course='CS101')

    assert len(filtered_from_list) == 2, f'Expected 2 results from list, got {len(filtered_from_list)}'
    assert len(filtered_from_set) == 2, f'Expected 2 results from set, got {len(filtered_from_set)}'
    print('✓ test_accepts_set_and_list passed')


def test_all_sentinel_uniqueness():
    """Test that ALL sentinel cannot match actual data."""
    test_keys = [
        ('CS101', 'RoomA', 'MWF-0830'),
    ]

    # ALL should not equal any string
    assert ALL != 'CS101', 'ALL should not equal course name'
    assert ALL != 'RoomA', 'ALL should not equal room name'
    assert ALL != 'MWF-0830', 'ALL should not equal time slot'
    assert ALL != None, 'ALL should not equal None'

    # ALL should only equal itself
    assert ALL is ALL, 'ALL should equal itself with identity check'

    print('✓ test_all_sentinel_uniqueness passed')


def test_scheduler_method_before_optimize():
    """Test that filter_schedule_keys raises error before optimize_schedule is called."""
    scheduler = InstructorScheduler()

    try:
        scheduler.filter_schedule_keys(course='CS101')
        assert False, 'Expected RuntimeError to be raised'
    except RuntimeError as e:
        assert 'optimize_schedule' in str(e), f'Error message should mention optimize_schedule: {e}'
        print('✓ test_scheduler_method_before_optimize passed')


def test_scheduler_method_integration():
    """Test the filter_schedule_keys method with actual scheduling data."""
    scheduler = InstructorScheduler()

    # Load data
    rooms = scheduler.load_rooms()
    courses = scheduler.load_courses()
    time_slots = scheduler.load_time_slots()

    if rooms is not None and courses is not None and time_slots is not None:
        # Run optimization
        scheduler.optimize_schedule()

        # Test filtering
        filtered = scheduler.filter_schedule_keys(course='ASEN-2402-001')
        assert isinstance(filtered, list), 'Should return a list'

        # All filtered keys should have the specified course
        if len(filtered) > 0:
            assert all(c == 'ASEN-2402-001' for c, r, t in filtered), \
                'All results should have course ASEN-2402-001'

        print('✓ test_scheduler_method_integration passed')
    else:
        print('⊘ test_scheduler_method_integration skipped (data files not available)')


def run_all_tests():
    """Run all tests."""
    print('Running filter_keys tests...\n')

    test_filter_by_course()
    test_filter_by_room()
    test_filter_by_time_slot()
    test_filter_by_multiple_criteria()
    test_filter_with_explicit_all()
    test_filter_no_matches()
    test_filter_with_predicate()
    test_accepts_set_and_list()
    test_all_sentinel_uniqueness()
    test_scheduler_method_before_optimize()
    test_scheduler_method_integration()

    print('\n' + '='*50)
    print('All tests passed! ✓')
    print('='*50)


if __name__ == '__main__':
    run_all_tests()
