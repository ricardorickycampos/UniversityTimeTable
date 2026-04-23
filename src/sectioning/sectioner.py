from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import numpy as np

from src.core.preprocessor import PreprocessedData

"""Greedy per-student section assignment.

Algorithm - Greedy, one student at a time:
  1. Iterate students in the given order.
  2. For each student, iterate their offerings.
  3. For each offering, iterate its subparts.
  4. For each subpart, find the "best" section among those that:
       - Don't conflict in time with what the student already has.
       - Have remaining capacity.
     "Best" = the section with the most remaining capacity (load-balancing).
  5. If no section fits, record it as an UNPLACED enrollment (soft penalty).
  6. If a section fits, assign the student and increment its enrollment count.
"""

@dataclass
class SectioningResult:
    assignment: dict = field(default_factory=dict)
    n_students_processed: int = 0
    n_enrollments_requested: int = 0
    n_enrollments_placed: int = 0
    n_enrollments_skipped: int = 0
    n_time_conflicts_avoided: int = 0
    n_capacity_rejections: int = 0
    final_section_enrollments: dict = field(default_factory=dict)




def build_offering_index(pp: PreprocessedData) -> dict:
    index: dict = {}
    for cls in pp.timetable.classes:
        index.setdefault(cls.offering, {}).setdefault(cls.subpart, []).append(cls.id)
    return index

def section_students(
    pp: PreprocessedData,
    phase1_assignment: np.ndarray,
    student_order: list,
    offering_index: Optional[dict] = None,
) -> SectioningResult:
    """Run greedy section assignment for all students in the given order."""
    tt = pp.timetable

    if offering_index is None:
        offering_index = build_offering_index(pp)

    class_time_mask: dict = {}
    class_idx_by_id = {c.id: i for i, c in enumerate(tt.classes)}
    for class_idx, cls in enumerate(tt.classes):
        if not cls.candidate_times:
            continue
        time_idx = int(phase1_assignment[class_idx, 1])
        class_time_mask[cls.id] = pp.time_masks[class_idx][time_idx]

    section_enrollments: dict = {cls.id: 0 for cls in tt.classes}

    result = SectioningResult(
        assignment={},
        final_section_enrollments=section_enrollments,
    )

    students_by_id = tt.students_by_id

    for student_id in student_order:
        student = students_by_id.get(student_id)
        if student is None:
            continue
        result.n_students_processed += 1

        student_mask_accum = None

        student_assignment: dict = {}

        for enrollment in student.enrollments:
            offering_id = enrollment.offering_id
            result.n_enrollments_requested += 1

            subparts = offering_index.get(offering_id, {})
            if not subparts:
                result.n_enrollments_skipped += 1
                continue

            subpart_choices: list = []
            subpart_masks: list = []
            all_subparts_ok = True

            for subpart_id, candidate_class_ids in subparts.items():
                chosen_class_id = _pick_best_section(
                    candidate_class_ids=candidate_class_ids,
                    student_mask_accum=student_mask_accum,
                    subpart_masks_so_far=subpart_masks,
                    class_time_mask=class_time_mask,
                    section_enrollments=section_enrollments,
                    pp=pp,
                    result=result,
                )

                if chosen_class_id is None:
                    all_subparts_ok = False
                    break

                subpart_choices.append(chosen_class_id)
                if chosen_class_id in class_time_mask:
                    subpart_masks.append(class_time_mask[chosen_class_id])

            if not all_subparts_ok:
                result.n_enrollments_skipped += 1
                continue

            for class_id in subpart_choices:
                section_enrollments[class_id] += 1
            for mask in subpart_masks:
                if student_mask_accum is None:
                    student_mask_accum = mask.copy()
                else:
                    student_mask_accum = student_mask_accum | mask
            student_assignment[offering_id] = subpart_choices
            result.n_enrollments_placed += 1

        if student_assignment:
            result.assignment[student_id] = student_assignment

    return result

def _pick_best_section(
    candidate_class_ids: list,
    student_mask_accum,
    subpart_masks_so_far: list,
    class_time_mask: dict,
    section_enrollments: dict,
    pp: PreprocessedData,
    result: SectioningResult,
) -> Optional[int]:
    """Choose the best section for one subpart, or return None if none fits.
    "Best" = the valid section with the MOST remaining capacity.
    """
    tt = pp.timetable

    best_class_id = None
    best_remaining_cap = -1

    for class_id in candidate_class_ids:
        cls = tt.classes_by_id[class_id]

        # Capacity check
        remaining_cap = cls.class_limit - section_enrollments[class_id]
        if remaining_cap <= 0:
            result.n_capacity_rejections += 1
            continue


        if class_id in class_time_mask:
            mask = class_time_mask[class_id]
            if student_mask_accum is not None:
                if np.any(student_mask_accum & mask):
                    result.n_time_conflicts_avoided += 1
                    continue

            conflict_with_siblings = False
            for sibling_mask in subpart_masks_so_far:
                if np.any(sibling_mask & mask):
                    conflict_with_siblings = True
                    break
            if conflict_with_siblings:
                result.n_time_conflicts_avoided += 1
                continue

        if remaining_cap > best_remaining_cap:
            best_remaining_cap = remaining_cap
            best_class_id = class_id

    return best_class_id

SKIP_PENALTY_PER_ENROLLMENT = 1000.0
"""Heavy penalty per missed (student, offering).
"""