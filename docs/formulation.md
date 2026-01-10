# Mathematical Formulation

Satisfaculty solves a course scheduling problem using Integer Linear Programming (ILP).

## Decision Variables

For each combination of course $c$, room $r$, and time slot $t$, we define a binary decision variable:

$$
x_{crt} \in \{0, 1\}
$$

where $x_{crt} = 1$ if course $c$ is assigned to room $r$ at time slot $t$.

## Constraints

### Assign All Courses

Each course must be assigned exactly once:

$$
\sum_{r \in R} \sum_{t \in T} x_{crt} = 1 \quad \forall c \in C
$$

### No Instructor Overlap

An instructor cannot teach two courses at the same time. For each instructor $i$ and time slot $t$:

$$
\sum_{c \in C_i} \sum_{r \in R} x_{crt} \leq 1 \quad \forall i \in I, \forall t \in T
$$

where $C_i$ is the set of courses taught by instructor $i$.

### No Room Overlap

A room cannot host two courses at the same time:

$$
\sum_{c \in C} x_{crt} \leq 1 \quad \forall r \in R, \forall t \in T
$$

### Room Capacity

Courses can only be assigned to rooms with sufficient capacity:

$$
x_{crt} = 0 \quad \text{if } \text{enrollment}_c > \text{capacity}_r
$$

## Lexicographic Optimization

Satisfaculty uses lexicographic optimization to handle multiple objectives in priority order. Given objectives $f_1, f_2, \ldots, f_n$, the algorithm:

1. Optimizes $f_1$ to find optimal value $f_1^*$
2. Adds constraint $f_1 = f_1^*$ (or within tolerance)
3. Optimizes $f_2$ subject to the $f_1$ constraint
4. Repeats for remaining objectives

This ensures higher-priority objectives are never compromised for lower-priority ones.
