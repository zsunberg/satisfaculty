# Debugging the Schedule

When a course isn't being scheduled where you want it, finding the cause can seem daunting given all the interacting constraints and objectives. This guide provides a systematic process for identifying and resolving scheduling issues.

## Example Problem

Suppose you want C-101 scheduled before noon, but it keeps getting placed at 2:40 PM. How do you fix this?

## Step-by-Step Process

### 1. Add an Incentive Objective

First, ensure there's an objective that encourages the optimizer to place C-101 before noon:

```python
objectives = [
    # ... other objectives ...
    MinimizeClassesAfter("12:00", courses=["C-101"]),
]
```

Run the optimizer. If C-101 moves before noon, you're done!

### 2. Identify the Blocking Constraint or Objective

If C-101 is still scheduled after noon, something with **higher priority** is preventing it. The blocker must be a constraint or an objective that appears **before** your incentive objective in the list.

To find it:

- Review only the constraints and objectives **above** your incentive objective
- Try moving the incentive objective higher in the priority list
- Use [bisection search](https://en.wikipedia.org/wiki/Bisection_method) to efficiently narrow down which objective is blocking: move your incentive to the middle of the list, check if it's satisfied, then search the appropriate half

### 3. Resolve the Conflict

Once you've identified the blocking constraint or objective, consider:

- **Remove it** if it's no longer needed
- **Reduce its scope** (e.g., exempt certain instructors or courses from the constraint)
- **Lower its priority** by moving it after other objectives

## Common Pitfall: Adding Constraints to "Make Room"

When a course won't go where you want, it's tempting to add constraints or force other courses into specific slots to "make room."

**This approach cannot help.** Adding constraints to an optimization problem can never improve the optimal objective value. If there's a feasible way to place C-101 before noon, the optimizer will find it automatically.

Instead, improve the schedule by:

- **Refining objectives** to better match your goals
- **Removing constraints** that are blocking better solutions

## Courses That Are Not Being Scheduled

A constraint or objective may name a course that isn't in the schedule at all, either because it is marked in the `Ignore` column of the courses file or because it simply isn't offered this term. Rather than failing, satisfaculty drops that course from the constraint or objective and prints a warning:

```
Warning: No overlap for courses (C-101, C-102) refers to course 'C-102', which is
not being scheduled (ignored or not offered); it will be skipped
```

This means an administrator can mark a course as ignored without having to edit any Python code. Watch for the warnings, though: a `SameTimeSlot` or `MaximizeBackToBackCourses` with fewer than two courses left has nothing to do and is dropped entirely, which is also reported.

It is common to carry a list of courses from term to term when only some of them are offered in any given term. Those lists would warn every run, so pass `warn_missing=False` to silence them:

```python
# Ten structures courses that shouldn't overlap when offered; only a few run each term.
NoCourseOverlap(structures_courses, warn_missing=False)
```

`warn_missing` is accepted by `NoCourseOverlap`, `SameTimeSlot`, `MaximizeBackToBackCourses`, and the objectives that take a `courses` argument. Leave it at its default of `True` for lists where a missing course means a typo.
