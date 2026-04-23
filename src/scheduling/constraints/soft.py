from __future__ import annotations

import numpy as np

from src.core.preprocessor import PreprocessedData

"""Soft constraint penalty scoring.
"""


def score_preferences(pp: PreprocessedData, assignment: np.ndarray) -> float:
    tt = pp.timetable
    total = 0.0

    for class_idx, cls in enumerate(tt.classes):
        if cls.candidate_times:
            time_idx = int(assignment[class_idx, 1])
            total += cls.candidate_times[time_idx].pref

        if cls.candidate_rooms:
            room_idx = int(assignment[class_idx, 0])
            total += cls.candidate_rooms[room_idx].pref

    return total

CAPACITY_VIOLATION_PENALTY = 500.0


def score_capacity(pp: PreprocessedData, assignment: np.ndarray) -> float:
    from src.scheduling.constraints.hard import check_capacity
    count = check_capacity(pp, assignment)
    return count * CAPACITY_VIOLATION_PENALTY

DAILY_MINUTES_SOFT_CAP = 6 * 60
CONSECUTIVE_MINUTES_SOFT_CAP = 3 * 60
OVER_DAILY_PENALTY_PER_MINUTE = 0.05
OVER_CONSECUTIVE_PENALTY_PER_MINUTE = 0.10


def score_instructor_workload(
    pp: PreprocessedData,
    assignment: np.ndarray,
) -> float:
    tt = pp.timetable
    slots = tt.slots_per_day  # 288
    total_penalty = 0.0

    for instructor_id, class_idxs in pp.instructor_to_classes.items():
        if not class_idxs:
            continue

        combined = np.zeros(7 * slots, dtype=bool)
        for ci in class_idxs:
            time_idx = int(assignment[ci, 1])
            combined |= pp.time_masks[ci][time_idx]

        daily = combined.reshape(7, slots)

        for day in range(7):
            day_cells = int(daily[day].sum())
            day_minutes = day_cells * 5
            if day_minutes > DAILY_MINUTES_SOFT_CAP:
                over = day_minutes - DAILY_MINUTES_SOFT_CAP
                total_penalty += over * OVER_DAILY_PENALTY_PER_MINUTE


            longest_run = _longest_true_run(daily[day])
            run_minutes = longest_run * 5
            if run_minutes > CONSECUTIVE_MINUTES_SOFT_CAP:
                over = run_minutes - CONSECUTIVE_MINUTES_SOFT_CAP
                total_penalty += over * OVER_CONSECUTIVE_PENALTY_PER_MINUTE

    return total_penalty


def _longest_true_run(arr: np.ndarray) -> int:
    if not arr.any():
        return 0
    padded = np.concatenate(([False], arr, [False]))
    diffs = np.diff(padded.astype(np.int8))
    starts = np.where(diffs == 1)[0]
    ends = np.where(diffs == -1)[0]
    if len(starts) == 0:
        return 0
    return int((ends - starts).max())

def score_soft_penalties(
    pp: PreprocessedData,
    assignment: np.ndarray,
) -> dict[str, float]:
    """Run all soft-constraint scorers and return a breakdown.
    """
    breakdown = {
        'preferences':         score_preferences(pp, assignment),
        'instructor_workload': score_instructor_workload(pp, assignment),
        'capacity': score_capacity(pp, assignment),
    }
    breakdown['total'] = sum(breakdown.values())
    return breakdown