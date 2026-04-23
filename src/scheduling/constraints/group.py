from __future__ import annotations
from typing import Callable
import numpy as np
from src.core.models import is_required, is_prohibited

"""Group constraint checking."""

def _class_room_id(pp, class_idx, assignment):
    cls = pp.timetable.classes[class_idx]
    if not cls.candidate_rooms:
        return None
    return cls.candidate_rooms[int(assignment[class_idx, 0])].room_id


def _class_time(pp, class_idx, assignment):
    cls = pp.timetable.classes[class_idx]
    if not cls.candidate_times:
        return None
    return cls.candidate_times[int(assignment[class_idx, 1])]


def _class_mask(pp, class_idx, assignment):
    cls = pp.timetable.classes[class_idx]
    if not cls.candidate_times:
        return np.zeros(0, dtype=bool)
    return pp.time_masks[class_idx][int(assignment[class_idx, 1])]


def _end_slot(tp):
    return tp.start + tp.length


def check_same_room(pp, class_idxs, assignment):
    if len(class_idxs) < 2: return 0, 0.0
    room_ids = [_class_room_id(pp, ci, assignment) for ci in class_idxs]
    room_ids = [r for r in room_ids if r is not None]
    if not room_ids: return 0, 0.0
    from collections import Counter
    counts = Counter(room_ids)
    outliers = len(room_ids) - counts.most_common(1)[0][1]
    return (1 if outliers > 0 else 0, float(outliers))


def check_same_time(pp, class_idxs, assignment):
    if len(class_idxs) < 2: return 0, 0.0
    times = [_class_time(pp, ci, assignment) for ci in class_idxs]
    times = [t for t in times if t is not None]
    if len(times) < 2: return 0, 0.0
    ref = times[0]
    outliers = sum(1 for t in times[1:]
                   if (t.days, t.start, t.length) != (ref.days, ref.start, ref.length))
    return (1 if outliers > 0 else 0, float(outliers))


check_meet_with = check_same_time


def check_same_start(pp, class_idxs, assignment):
    if len(class_idxs) < 2: return 0, 0.0
    times = [_class_time(pp, ci, assignment) for ci in class_idxs]
    times = [t for t in times if t is not None]
    if len(times) < 2: return 0, 0.0
    ref_start = times[0].start
    outliers = sum(1 for t in times[1:] if t.start != ref_start)
    return (1 if outliers > 0 else 0, float(outliers))


def check_same_days(pp, class_idxs, assignment):
    if len(class_idxs) < 2: return 0, 0.0
    times = [_class_time(pp, ci, assignment) for ci in class_idxs]
    times = [t for t in times if t is not None]
    if len(times) < 2: return 0, 0.0
    ref_days = times[0].days
    outliers = sum(1 for t in times[1:] if t.days != ref_days)
    return (1 if outliers > 0 else 0, float(outliers))


def check_same_instr(pp, class_idxs, assignment):
    if len(class_idxs) < 2: return 0, 0.0
    sets = [set(pp.timetable.classes[ci].instructor_ids) for ci in class_idxs]
    common = sets[0]
    for s in sets[1:]:
        common &= s
    broken = len(common) == 0
    return (1 if broken else 0, 1.0 if broken else 0.0)


def check_diff_time(pp, class_idxs, assignment):
    if len(class_idxs) < 2: return 0, 0.0
    masks = [_class_mask(pp, ci, assignment) for ci in class_idxs]
    overlap = 0
    for i in range(len(class_idxs)):
        if masks[i].size == 0: continue
        for j in range(i+1, len(class_idxs)):
            if masks[j].size == 0: continue
            if np.any(masks[i] & masks[j]):
                overlap += 1
    return (1 if overlap > 0 else 0, float(overlap))


check_same_students = check_diff_time


def check_btb(pp, class_idxs, assignment):
    if len(class_idxs) < 2: return 0, 0.0
    times = [_class_time(pp, ci, assignment) for ci in class_idxs]
    if any(t is None for t in times): return 0, 0.0
    bad = 0
    for i in range(len(times)-1):
        a, b = times[i], times[i+1]
        if (a.days & b.days) == 0:
            bad += 1
            continue
        if not (_end_slot(a) == b.start or _end_slot(b) == a.start):
            bad += 1
    return (1 if bad > 0 else 0, float(bad))


check_btb_time = check_btb


def _check_hours_between(pp, class_idxs, assignment, target_hours, mode):
    if len(class_idxs) < 2: return 0, 0.0
    times = [_class_time(pp, ci, assignment) for ci in class_idxs]
    if any(t is None for t in times): return 0, 0.0
    target_slots = int(target_hours * 12)
    dev = 0
    for i in range(len(times)-1):
        a, b = times[i], times[i+1]
        if (a.days & b.days) == 0:
            dev += target_slots
            continue
        gap = b.start - _end_slot(a)
        if gap < 0:
            gap = a.start - _end_slot(b)
            if gap < 0: gap = 0
        if mode == 'exact':
            dev += abs(gap - target_slots)
        else:
            dev += max(0, target_slots - gap)
    return (1 if dev > 0 else 0, float(dev))


def check_nhb_exact_15(pp, ci, a):
    return _check_hours_between(pp, ci, a, 1.5, 'exact')

def check_nhb_gte_1(pp, ci, a):
    return _check_hours_between(pp, ci, a, 1.0, 'gte')

def check_can_share_room(pp, ci, a):
    return 0, 0.0

def check_spread(pp, class_idxs, assignment):
    if len(class_idxs) < 2: return 0, 0.0
    times = [_class_time(pp, ci, assignment) for ci in class_idxs]
    times = [t for t in times if t is not None]
    day_counts = [0]*7
    for t in times:
        for db in range(7):
            if t.days & (1 << db):
                day_counts[db] += 1
    mag = sum(max(0, c-1) for c in day_counts)
    return (1 if mag > 0 else 0, float(mag))

_DISPATCH: dict[str, Callable] = {
    'SAME_ROOM': check_same_room, 'SAME_TIME': check_same_time,
    'MEET_WITH': check_meet_with, 'SAME_START': check_same_start,
    'SAME_DAYS': check_same_days, 'SAME_INSTR': check_same_instr,
    'DIFF_TIME': check_diff_time, 'SAME_STUDENTS': check_same_students,
    'BTB': check_btb, 'BTB_TIME': check_btb_time,
    'NHB(1.5)': check_nhb_exact_15, 'NHB_GTE(1)': check_nhb_gte_1,
    'CAN_SHARE_ROOM': check_can_share_room, 'SPREAD': check_spread,
}

def check_group_constraint(pp, gc_idx, assignment):
    gc = pp.timetable.group_constraints[gc_idx]
    handler = _DISPATCH.get(gc.type)
    if handler is None: return 0, 0.0
    return handler(pp, pp.gc_to_classes[gc_idx], assignment)

R_PREF_GROUP_WEIGHT = 200.0


def check_all_group_constraints(pp, assignment):
    """Run all group constraints and return hard + soft breakdowns.
    """
    hard_count = 0
    hard_detail = []
    soft_penalty = 0.0
    soft_detail = []

    for gc_idx, gc in enumerate(pp.timetable.group_constraints):
        count, magnitude = check_group_constraint(pp, gc_idx, assignment)

        if count == 0:
            continue

        if is_prohibited(gc.pref):
            hard_count += 1
            hard_detail.append((gc.id, gc.type, magnitude))

        elif is_required(gc.pref):
            contribution = R_PREF_GROUP_WEIGHT * magnitude
            soft_penalty += contribution
            soft_detail.append((gc.id, gc.type, magnitude, 'R', contribution))

        else:
            contribution = abs(gc.pref) * magnitude
            soft_penalty += contribution
            soft_detail.append((gc.id, gc.type, magnitude, gc.pref, contribution))

    return {
        'hard_count':   hard_count,
        'hard_detail':  hard_detail,
        'soft_penalty': soft_penalty,
        'soft_detail':  soft_detail,
    }