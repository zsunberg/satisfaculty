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


def time_to_minutes(time_str):
    """Convert time string HH:MM to minutes since midnight."""
    h, m = map(int, time_str.split(':'))
    return h * 60 + m


def minutes_to_time(minutes):
    """Convert minutes since midnight to time string HH:MM."""
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


def expand_days(days_str):
    """Expand day codes to individual days. MWF -> [M, W, F], TTH -> [T, TH]"""
    if days_str == "MWF":
        return ['M', 'W', 'F']
    elif days_str == "TTH":
        return ['T', 'TH']
    else:
        # Single day (M, T, W, TH, F)
        return [days_str]


def visualize_schedule(schedule_df, rooms_df, output_file='output/schedule_visual.png'):
    """Create a visual grid representation of the schedule."""

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
                'Instructor': row['Instructor']
            })

    schedule_exp_df = pd.DataFrame(schedule_expanded)

    # Get room info with capacity
    room_capacity = dict(zip(rooms_df['Room'], rooms_df['Capacity']))
    rooms = sorted(schedule_exp_df['Room'].unique(),
                   key=lambda r: room_capacity.get(r, 0), reverse=False)  # Ascending for matplotlib (displays bottom-to-top)

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

    # Color map for courses
    unique_courses = schedule_exp_df['Course'].unique()
    colors = plt.cm.tab20(np.linspace(0, 1, len(unique_courses)))
    course_colors = dict(zip(unique_courses, colors))

    for day_idx, day in enumerate(days):
        ax = axes[day_idx]

        day_schedule = schedule_exp_df[schedule_exp_df['Day'] == day]

        # Set up the plot
        ax.set_xlim(min_time, max_time)
        ax.set_ylim(-0.5, len(rooms) - 0.5)

        # Draw grid
        for i in range(len(rooms) + 1):
            ax.axhline(i - 0.5, color='gray', linewidth=0.5)

        # Draw hour lines
        for hour in range(min_time // 60, max_time // 60 + 1):
            ax.axvline(hour * 60, color='gray', linewidth=0.5, alpha=0.3)

        # Plot courses
        for _, course in day_schedule.iterrows():
            room_idx = rooms.index(course['Room'])
            start = course['StartMin']
            duration = course['EndMin'] - course['StartMin']

            # Draw rectangle
            rect = Rectangle((start, room_idx - 0.4), duration, 0.8,
                            facecolor=course_colors[course['Course']],
                            edgecolor='black', linewidth=1)
            ax.add_patch(rect)

            # Add course text
            text_x = start + duration / 2
            text_y = room_idx
            ax.text(text_x, text_y, course['Course'],
                   ha='center', va='center', fontsize=8, weight='bold')

        # Set room labels
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
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"\nSchedule visualization saved to {output_file}")
    plt.close()


def main():
    """Load schedule and create visualization."""
    print("Loading schedule data...")
    schedule_df = pd.read_csv('output/schedule.csv')
    rooms_df = pd.read_csv('data/rooms.csv')

    print(f"Loaded {len(schedule_df)} scheduled courses")

    visualize_schedule(schedule_df, rooms_df)
    print("Visualization complete!")


if __name__ == "__main__":
    main()
