#!/usr/bin/env python3
"""
Schedule Visualization
Creates a visual grid showing course schedules by day, room, and time.
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Rectangle
from datetime import datetime, timedelta
import numpy as np
from .utils import time_to_minutes, minutes_to_time, expand_days


def _intervals_overlap(intervals_a, intervals_b):
    """Check if any interval in A overlaps with any interval in B."""
    for (start_a, end_a) in intervals_a:
        for (start_b, end_b) in intervals_b:
            if start_a < end_b and start_b < end_a:
                return True
    return False


def _compute_merged_rows(day_schedule, rooms, room_capacity, mergeable_rooms=None):
    """
    Compute merged row assignments using greedy bin-packing.

    Args:
        day_schedule: DataFrame of courses for a single day
        rooms: List of room names sorted by capacity
        room_capacity: Dict mapping room name to capacity
        mergeable_rooms: Set of room names that can be merged, or None to merge all

    Returns:
        merged_rows: List of sets of room names sharing each row
        room_to_row_idx: Dict mapping room name to row index
    """
    # Get intervals for each room on this day
    room_intervals = {}
    for _, course in day_schedule.iterrows():
        room = course['Room']
        if room not in room_intervals:
            room_intervals[room] = []
        room_intervals[room].append((course['StartMin'], course['EndMin']))

    merged_rows = []  # List of (set of rooms, combined intervals)
    room_to_row_idx = {}

    # Process rooms in capacity order for consistent behavior
    for room in rooms:
        # Check if this room is allowed to be merged
        can_merge = mergeable_rooms is None or room in mergeable_rooms

        # Skip rooms with no courses IF they are mergeable
        # Non-mergeable rooms always get their own row
        if room not in room_intervals:
            if can_merge:
                continue  # Mergeable room with no courses - skip it
            else:
                # Non-mergeable room with no courses - still give it a row
                room_to_row_idx[room] = len(merged_rows)
                merged_rows.append(({room}, []))
                continue

        intervals = room_intervals[room]
        placed = False

        if can_merge:
            # Try to fit into existing merged row (only with other mergeable rooms)
            for row_idx, (row_rooms, row_intervals) in enumerate(merged_rows):
                # Only merge if all rooms in this row are also mergeable
                all_mergeable = mergeable_rooms is None or all(r in mergeable_rooms for r in row_rooms)
                if all_mergeable and not _intervals_overlap(intervals, row_intervals):
                    row_rooms.add(room)
                    row_intervals.extend(intervals)
                    room_to_row_idx[room] = row_idx
                    placed = True
                    break

        if not placed:
            room_to_row_idx[room] = len(merged_rows)
            merged_rows.append(({room}, list(intervals)))

    # Extract just the room sets
    return [row_rooms for row_rooms, _ in merged_rows], room_to_row_idx


def visualize_schedule(schedule_df, rooms_df, output_file='schedule_visual.png', merge_rows=None, room_order=None, highlight_changes_from=None, highlight_time_changes_from=None):
    """
    Create a visual grid representation of the schedule.

    Args:
        schedule_df: DataFrame with schedule data
        rooms_df: DataFrame with room data
        output_file: Path to save the visualization PNG
        merge_rows: Controls row merging behavior:
            - None or False: No merging, one row per room
            - True: Merge all non-overlapping rooms
            - List of room names: Only merge the specified rooms if they don't overlap
        room_order: Controls room display order (top to bottom on the plot):
            - None: Sort by capacity (largest at top, default)
            - List of room names: Display in the specified order (first = top)
        highlight_changes_from: Optional previous schedule to compare against:
            - None: No highlighting
            - str: Path to a CSV file with the previous schedule
            - DataFrame: Previous schedule DataFrame
            Courses that changed room or time slot will be highlighted with an orange border.
        highlight_time_changes_from: Optional previous schedule to compare against:
            - None: No highlighting
            - str: Path to a CSV file with the previous schedule
            - DataFrame: Previous schedule DataFrame
            Only courses that changed time slot (ignoring room) will be highlighted with an orange border.
    """

    # Normalize merge_rows parameter
    if merge_rows is False:
        merge_rows = None
    mergeable_rooms = None
    if isinstance(merge_rows, list):
        mergeable_rooms = set(merge_rows)
    elif merge_rows is True:
        mergeable_rooms = None  # None means all rooms can merge

    # Load previous schedule and build set of changed courses
    changed_courses = set()
    if highlight_changes_from is not None:
        if isinstance(highlight_changes_from, str):
            prev_df = pd.read_csv(highlight_changes_from)
        else:
            prev_df = highlight_changes_from

        # Build lookup of previous assignments: course -> (room, slot)
        prev_assignments = {}
        for _, row in prev_df.iterrows():
            prev_assignments[row['Course']] = (row['Room'], row['Slot'])

        # Find courses that changed
        for _, row in schedule_df.iterrows():
            course = row['Course']
            if course in prev_assignments:
                prev_room, prev_slot = prev_assignments[course]
                if row['Room'] != prev_room or row['Slot'] != prev_slot:
                    changed_courses.add(course)
            else:
                # New course not in previous schedule
                changed_courses.add(course)

    elif highlight_time_changes_from is not None:
        if isinstance(highlight_time_changes_from, str):
            prev_df = pd.read_csv(highlight_time_changes_from)
        else:
            prev_df = highlight_time_changes_from

        # Build lookup of previous assignments: course -> slot
        prev_slots = {}
        for _, row in prev_df.iterrows():
            prev_slots[row['Course']] = row['Slot']

        # Find courses that changed time slot
        for _, row in schedule_df.iterrows():
            course = row['Course']
            if course in prev_slots:
                if row['Slot'] != prev_slots[course]:
                    changed_courses.add(course)
            else:
                # New course not in previous schedule
                changed_courses.add(course)

    # Expand schedule to have one row per day
    schedule_expanded = []
    for _, row in schedule_df.iterrows():
        for day in expand_days(row['Days']):
            schedule_expanded.append({
                'Course': row['Course'],
                'Room': row['Room'],
                'Day': day,
                'Start': row['Start'],
                'End': row['End'],
                'Instructor': row['Instructor'],
                'Enrollment': row['Enrollment']
            })

    schedule_exp_df = pd.DataFrame(schedule_expanded)

    # Get room info with capacity
    room_capacity = dict(zip(rooms_df['Room'], rooms_df['Capacity']))
    all_rooms = set(rooms_df['Room'])

    # Determine room order
    # Note: matplotlib plots y-axis bottom-to-top, so we reverse to get top-to-bottom display
    scheduled_rooms = set(schedule_exp_df['Room'].unique())

    # When merge_rows is a list, non-mergeable rooms should always be shown
    # So we need to include them even if they have no scheduled classes
    if mergeable_rooms is not None:
        # Include: scheduled rooms + non-mergeable rooms from the full room list
        rooms_to_show = scheduled_rooms | (all_rooms - mergeable_rooms)
    else:
        rooms_to_show = scheduled_rooms

    if room_order is not None:
        # Use specified order, include rooms even if not scheduled (if non-mergeable)
        rooms = [r for r in room_order if r in rooms_to_show]
        # Append any rooms not in room_order (sorted by capacity descending)
        remaining = sorted(
            [r for r in rooms_to_show if r not in room_order],
            key=lambda r: room_capacity.get(r, 0),
            reverse=True
        )
        rooms = rooms + remaining
        # Reverse so first in list appears at top (highest y-index)
        rooms = list(reversed(rooms))
    else:
        # Default: sort by capacity ascending so largest is at top
        rooms = sorted(rooms_to_show, key=lambda r: room_capacity.get(r, 0))

    # Define day order
    day_order = ['M', 'T', 'W', 'TH', 'F']
    days = [d for d in day_order if d in schedule_exp_df['Day'].unique()]

    # Find time range
    schedule_exp_df['StartMin'] = schedule_exp_df['Start'].apply(time_to_minutes)
    schedule_exp_df['EndMin'] = schedule_exp_df['End'].apply(time_to_minutes)
    min_time = schedule_exp_df['StartMin'].min()
    max_time = schedule_exp_df['EndMin'].max()

    # Round to nearest hour for display
    min_time = (min_time // 60) * 60
    max_time = ((max_time // 60) + 1) * 60

    # Create figure
    fig, axes = plt.subplots(len(days), 1, figsize=(20, 4 * len(days)))
    if len(days) == 1:
        axes = [axes]

    # Color map by year level (matching original visualization)
    year_colors = {
        1000: '#FFFFFF',  # White
        2000: '#9BC2E6',  # Light blue
        3000: '#A9D08E',  # Light green
        4000: '#D9B3FF',  # Light purple
        5000: '#FFD85D',  # Light yellow
        6000: '#F1995D',  # Light orange
    }

    def get_course_color(course_name):
        """Extract year level from course code and return color."""
        # Extract number (e.g., "DEPT-2402-001" -> "2402")
        parts = course_name.split('-')
        if len(parts) >= 2 and parts[1].isdigit():
            course_number = int(parts[1])
            year_level = (course_number // 1000) * 1000  # Round down to thousand
            return year_colors.get(year_level, '#BBBBBB')  # Gray for unknown
        return '#BBBBBB'  # Gray default

    course_colors = {course: get_course_color(course)
                     for course in schedule_exp_df['Course'].unique()}

    for day_idx, day in enumerate(days):
        ax = axes[day_idx]

        day_schedule = schedule_exp_df[schedule_exp_df['Day'] == day]

        # Determine row mapping based on merge_rows option
        if merge_rows:
            merged_row_sets, room_to_row_idx = _compute_merged_rows(
                day_schedule, rooms, room_capacity, mergeable_rooms
            )
            num_rows = len(merged_row_sets)
            if num_rows == 0:
                num_rows = 1  # Avoid empty plot
            # Build set of rooms that are actually in merged rows (more than one room)
            rooms_in_merged_rows = set()
            for row_rooms in merged_row_sets:
                if len(row_rooms) > 1:
                    rooms_in_merged_rows.update(row_rooms)
        else:
            room_to_row_idx = {room: idx for idx, room in enumerate(rooms)}
            num_rows = len(rooms)
            merged_row_sets = None
            rooms_in_merged_rows = set()

        # Set up the plot
        ax.set_xlim(min_time, max_time)
        ax.set_ylim(-0.5, num_rows - 0.5)

        # Draw horizontal lines between rooms (behind boxes)
        for i in range(num_rows + 1):
            ax.axhline(i - 0.5, color='gray', linewidth=0.5)

        # Plot courses
        for _, course in day_schedule.iterrows():
            room_idx = room_to_row_idx[course['Room']]
            start = course['StartMin']
            duration = course['EndMin'] - course['StartMin']

            # Draw rectangle (highlight changed courses with orange border)
            is_changed = course['Course'] in changed_courses
            edge_color = 'orange' if is_changed else 'black'
            edge_width = 3 if is_changed else 1
            rect = Rectangle((start, room_idx - 0.4), duration, 0.8,
                            facecolor=course_colors[course['Course']],
                            edgecolor=edge_color, linewidth=edge_width)
            ax.add_patch(rect)

            # Add course text
            text_x = start + duration / 2
            text_y = room_idx

            # Only show room name in box if this room is in a merged row
            if course['Room'] in rooms_in_merged_rows:
                # Two-line label: Course, (Room, Instructor, Enrollment)
                ax.text(text_x, text_y + 0.15, course['Course'],
                       ha='center', va='center', fontsize=8, weight='bold')
                ax.text(text_x, text_y - 0.15,
                       f"{course['Room']} ({course['Instructor']}, {int(course['Enrollment'])})",
                       ha='center', va='center', fontsize=7)
            else:
                # Original two-line label
                ax.text(text_x, text_y + 0.15, course['Course'],
                       ha='center', va='center', fontsize=8, weight='bold')
                ax.text(text_x, text_y - 0.15, f"({course['Instructor']}, {int(course['Enrollment'])})",
                       ha='center', va='center', fontsize=7)

        # Draw vertical hour lines (in front of boxes)
        for hour in range(min_time // 60, max_time // 60 + 1):
            ax.axvline(hour * 60, color='gray', linewidth=0.5, alpha=0.3)

        # Set room labels
        if merge_rows and merged_row_sets:
            row_labels = []
            for row_rooms in merged_row_sets:
                if len(row_rooms) == 1:
                    room = list(row_rooms)[0]
                    row_labels.append(f"{room} ({room_capacity.get(room, '?')})")
                else:
                    row_labels.append(f"Merged: {len(row_rooms)} rooms")
            ax.set_yticks(range(num_rows))
            ax.set_yticklabels(row_labels)
        else:
            room_labels = [f"{room} ({room_capacity.get(room, '?')})" for room in rooms]
            ax.set_yticks(range(len(rooms)))
            ax.set_yticklabels(room_labels)

        # Set time labels
        time_ticks = range(min_time, max_time + 1, 60)
        ax.set_xticks(time_ticks)
        ax.set_xticklabels([minutes_to_time(t) for t in time_ticks])

        # Format
        day_names = {'M': 'MONDAY', 'T': 'TUESDAY', 'W': 'WEDNESDAY',
                    'TH': 'THURSDAY', 'F': 'FRIDAY'}
        ax.set_title(day_names.get(day, day), fontsize=14, weight='bold')
        ax.set_xlabel('Time')
        ax.set_ylabel('Room (Capacity)')

    plt.tight_layout()
    import os
    dirname = os.path.dirname(output_file)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"\nSchedule visualization saved to {output_file}")
    plt.close()


def main():
    """Load schedule and create visualization."""
    print("Loading schedule data...")
    schedule_df = pd.read_csv('schedule.csv')
    rooms_df = pd.read_csv('rooms.csv')

    print(f"Loaded {len(schedule_df)} scheduled courses")

    visualize_schedule(schedule_df, rooms_df)
    print("Visualization complete!")


if __name__ == "__main__":
    main()
