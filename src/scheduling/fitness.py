from __future__ import annotations

import numpy as np
from src.core.preprocessor import PreprocessedData
from src.scheduling.constraints.hard import count_hard_violations
from src.scheduling.constraints.soft import score_soft_penalties
from src.scheduling.constraints.group import check_all_group_constraints

"""Aggregate hard and soft constraint scores into one fitness number."""
def evaluate_detailed(
    pp: PreprocessedData,
    assignment: np.ndarray,
    hard_weight: float = 1000.0,
) -> dict:
    """Returns:
        Dict with structure of all the broken constraints and total score.
    """
    hard_breakdown = count_hard_violations(pp, assignment)
    soft_breakdown = score_soft_penalties(pp, assignment)
    group_result = check_all_group_constraints(pp, assignment)
    hard = {
        'room_conflicts':       hard_breakdown['room_conflicts'],
        'instructor_conflicts': hard_breakdown['instructor_conflicts'],
        'room_sharing':         hard_breakdown['room_sharing'],
        'group':                group_result['hard_count'],
    }
    hard['total'] = sum(hard.values())

    soft = {
        'preferences':         soft_breakdown['preferences'],
        'instructor_workload': soft_breakdown['instructor_workload'],
        'group':               group_result['soft_penalty'],
        'capacity':             soft_breakdown['capacity'],
    }
    soft['total'] = sum(soft.values())

    # The scalar fitness value.
    fitness = hard_weight * hard['total'] + soft['total']

    return {
        'fitness':     float(fitness),
        'hard_total':  hard['total'],
        'soft_total':  soft['total'],
        'hard':        hard,
        'soft':        soft,
        'is_feasible': hard['total'] == 0,
    }

def evaluate(
    pp: PreprocessedData,
    assignment: np.ndarray,
    hard_weight: float = 1000.0,
) -> float:
    """Compute just the scalar fitness value.
    """
    return evaluate_detailed(pp, assignment, hard_weight)['fitness']