"""Phase 2 fitness: scoring a student processing order.


fitness = skip_weight * n_skipped
        + conflict_weight * n_time_conflicts_avoided
        + capacity_weight * n_capacity_rejections_observed

Where:
  n_skipped: student offering pairs the sectioner couldn't fill.
  n_time_conflicts_avoided: candidate sections rejected because they'd
    overlap with a student's existing schedule.
  n_capacity_rejections: candidate sections rejected because already full.
"""
from __future__ import annotations

import numpy as np
from src.core.preprocessor import PreprocessedData
from src.sectioning.sectioner import (
    section_students,
    build_offering_index,
    SKIP_PENALTY_PER_ENROLLMENT,
)

CONFLICT_REJECT_WEIGHT = 5.0
CAPACITY_REJECT_WEIGHT = 5.0

def evaluate(
    pp: PreprocessedData,
    phase1_assignment: np.ndarray,
    chromosome: list,
    offering_index: dict = None,
) -> float:
    """Compute the scalar fitness for one student-order chromosome.
    """
    if offering_index is None:
        offering_index = build_offering_index(pp)

    result = section_students(
        pp=pp,
        phase1_assignment=phase1_assignment,
        student_order=chromosome,
        offering_index=offering_index,
    )

    fitness = (
        SKIP_PENALTY_PER_ENROLLMENT * result.n_enrollments_skipped
        + CONFLICT_REJECT_WEIGHT * result.n_time_conflicts_avoided
        + CAPACITY_REJECT_WEIGHT * result.n_capacity_rejections
    )
    return float(fitness)


def evaluate_detailed(
    pp: PreprocessedData,
    phase1_assignment: np.ndarray,
    chromosome: list,
    offering_index: dict = None,
) -> dict:
    """Compute full fitness breakdown for logging and reporting.
    """
    if offering_index is None:
        offering_index = build_offering_index(pp)

    result = section_students(
        pp=pp,
        phase1_assignment=phase1_assignment,
        student_order=chromosome,
        offering_index=offering_index,
    )

    # Penalty component breakdown
    skip_pen     = SKIP_PENALTY_PER_ENROLLMENT * result.n_enrollments_skipped
    conflict_pen = CONFLICT_REJECT_WEIGHT * result.n_time_conflicts_avoided
    cap_pen      = CAPACITY_REJECT_WEIGHT * result.n_capacity_rejections
    total = skip_pen + conflict_pen + cap_pen

    coverage = (
        100.0 * result.n_enrollments_placed / result.n_enrollments_requested
        if result.n_enrollments_requested > 0 else 0.0
    )

    return {
        'fitness':               float(total),
        'n_students':            result.n_students_processed,
        'enrollments_total':     result.n_enrollments_requested,
        'enrollments_placed':    result.n_enrollments_placed,
        'enrollments_skipped':   result.n_enrollments_skipped,
        'coverage_pct':          coverage,
        'conflict_rejects':      result.n_time_conflicts_avoided,
        'capacity_rejects':      result.n_capacity_rejections,
        'penalty_breakdown': {
            'skips':    float(skip_pen),
            'conflicts': float(conflict_pen),
            'capacity': float(cap_pen),
            'total':    float(total),
        },
        'result': result,
    }