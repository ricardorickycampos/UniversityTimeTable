from __future__ import annotations

import numpy as np
from src.core.preprocessor import PreprocessedData

"""Hard constraint violation counting.
"""

def check_room_conflicts(pp: PreprocessedData, assignment: np.ndarray) -> int:
    tt = pp.timetable
    n_classes = len(tt.classes)

    classes_by_room: dict = {}
    for class_idx in range(n_classes):
        cls = tt.classes[class_idx]
        if not cls.candidate_rooms:
            continue
        room_idx = int(assignment[class_idx, 0])
        room_id = cls.candidate_rooms[room_idx].room_id
        classes_by_room.setdefault(room_id, []).append(class_idx)

    violations = 0
    for room_id, class_idxs in classes_by_room.items():
        if len(class_idxs) < 2:
            continue

        masks = [
            pp.time_masks[ci][int(assignment[ci, 1])]
            for ci in class_idxs
        ]

        for i in range(len(class_idxs)):
            for j in range(i + 1, len(class_idxs)):
                ci_a = class_idxs[i]
                ci_b = class_idxs[j]
                key = (min(ci_a, ci_b), max(ci_a, ci_b))
                if key in pp.meet_with_exempt_pairs:
                    continue

                if np.any(masks[i] & masks[j]):
                    violations += 1
    return violations


def check_instructor_conflicts(pp: PreprocessedData, assignment: np.ndarray) -> int:
    violations = 0

    for instructor_id, class_idxs in pp.instructor_to_classes.items():
        if len(class_idxs) < 2:
            continue

        masks = [
            pp.time_masks[ci][int(assignment[ci, 1])]
            for ci in class_idxs
        ]

        for i in range(len(class_idxs)):
            for j in range(i + 1, len(class_idxs)):
                ci_a = class_idxs[i]
                ci_b = class_idxs[j]
                key = (min(ci_a, ci_b), max(ci_a, ci_b))
                if key in pp.meet_with_exempt_pairs:
                    continue

                if np.any(masks[i] & masks[j]):
                    violations += 1

    return violations


def check_capacity(pp: PreprocessedData, assignment: np.ndarray) -> int:
    tt = pp.timetable
    violations = 0
    for class_idx, cls in enumerate(tt.classes):
        if not cls.candidate_rooms:
            continue
        room_id = cls.candidate_rooms[int(assignment[class_idx, 0])].room_id
        room = tt.rooms_by_id[room_id]
        if cls.class_limit > room.capacity:
            violations += 1
    return violations


def check_room_sharing(pp: PreprocessedData, assignment: np.ndarray) -> int:
    tt = pp.timetable
    violations = 0

    if not any(r.sharing is not None for r in tt.rooms):
        return 0

    for class_idx, cls in enumerate(tt.classes):
        if not cls.candidate_rooms:
            continue
        room_id = cls.candidate_rooms[int(assignment[class_idx, 0])].room_id
        room = tt.rooms_by_id[room_id]

        if room.sharing is None:
            continue


        dept_to_char = {v: k for k, v in room.sharing.departments.items()}
        class_char = dept_to_char.get(cls.department)

        pattern = room.sharing.pattern
        unit_cells = room.sharing.unit_minutes // 5
        time_idx = int(assignment[class_idx, 1])
        mask = pp.time_masks[class_idx][time_idx]

        class_violated = False
        for cell in np.where(mask)[0]:
            pattern_idx = cell // unit_cells
            if pattern_idx >= len(pattern):
                continue
            ch = pattern[pattern_idx]
            if ch == 'F':
                continue
            if ch == 'X':
                class_violated = True
                break
            if class_char is None or ch != class_char:
                class_violated = True
                break

        if class_violated:
            violations += 1

    return violations


def count_hard_violations(pp: PreprocessedData, assignment: np.ndarray) -> dict:
    breakdown = {
        'room_conflicts':        check_room_conflicts(pp, assignment),
        'instructor_conflicts':  check_instructor_conflicts(pp, assignment),
        'room_sharing':          check_room_sharing(pp, assignment),
    }
    breakdown['total'] = sum(breakdown.values())
    return breakdown