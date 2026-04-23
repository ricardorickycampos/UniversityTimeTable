from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np
from src.core.models import Timetable


CONFLICT_IMPLYING_TYPES = {'SAME_STUDENTS', 'DIFF_TIME'}


@dataclass
class PreprocessedData:
    """Everything derived from a Timetable, cached for fast access using maps and arrays.
    Ease of use for the GA engine.
    """
    timetable: Timetable
    time_masks: list = field(default_factory=list)
    instructor_to_classes: dict = field(default_factory=dict) # list of class_idx that instructor teaches
    gc_to_classes: list = field(default_factory=list) # list of class_idx (parallel to timetable.group_constraints)
    class_to_gcs: list = field(default_factory=list)
    conflict_graph: list = field(default_factory=list) #  set of class_idx it conflicts with
    dsatur_order: list = field(default_factory=list) # Class indices, most conflicting to least (for population seeding)
    meet_with_exempt_pairs: set = field(default_factory=set)

def _make_time_mask(pattern, slots_per_day=288):
    """Build a flat bool array marking which 5-min week cells this pattern fills.
    Week = 7 days x 288 slots = 2016 cells total.
    """
    mask = np.zeros(7 * slots_per_day, dtype=bool)
    for day_bit in range(7):
        if pattern.days & (1 << day_bit):
            day_offset = day_bit * slots_per_day
            mask[day_offset + pattern.start : day_offset + pattern.start + pattern.length] = True
    return mask


def _build_time_masks(tt):
    """For each class, stack all candidate time masks into a 2D array.
    time_masks[class_idx] has shape (n_times, 2016).
    """
    slots = tt.slots_per_day
    out = []
    for c in tt.classes:
        if not c.candidate_times:
            out.append(np.zeros((0, 7 * slots), dtype=bool))
            continue
        stack = np.stack([_make_time_mask(t, slots) for t in c.candidate_times])
        out.append(stack)
    return out


def _build_instructor_index(tt):
    """Map each instructor_id to the list of class indices they teach.
    classes that have no instructor are ignored.
    instructors that teach 2+ classes create conflict check pairs.
    """
    idx: dict = {}
    for class_idx, c in enumerate(tt.classes):
        for instr_id in c.instructor_ids:
            idx.setdefault(instr_id, []).append(class_idx)
    return idx


def _build_gc_indices(tt):
    """Builds Look up tables for GC indices and class indices."""
    class_id_to_idx = {c.id: i for i, c in enumerate(tt.classes)}
    gc_to_classes: list = []
    class_to_gcs: list = [[] for _ in tt.classes]

    for gc_idx, gc in enumerate(tt.group_constraints):
        class_idxs = [
            class_id_to_idx[cid]
            for cid in gc.class_ids
            if cid in class_id_to_idx
        ]
        gc_to_classes.append(class_idxs)
        for ci in class_idxs:
            class_to_gcs[ci].append(gc_idx)

    return gc_to_classes, class_to_gcs


def _build_conflict_graph(tt, instructor_to_classes, gc_to_classes):
    """Adjacency sets for classes that must NOT share a timeslot.
    From Data: Constraint
        @shared instructor
        @SAME_STUDENTS
        @DIFF_TIME
    """
    graph: list = [set() for _ in tt.classes]

    for class_idxs in instructor_to_classes.values():
        for i in range(len(class_idxs)):
            for j in range(i + 1, len(class_idxs)):
                a, b = class_idxs[i], class_idxs[j]
                graph[a].add(b)
                graph[b].add(a)

    for gc_idx, gc in enumerate(tt.group_constraints):
        if gc.type not in CONFLICT_IMPLYING_TYPES:
            continue
        idxs = gc_to_classes[gc_idx]
        for i in range(len(idxs)):
            for j in range(i + 1, len(idxs)):
                a, b = idxs[i], idxs[j]
                graph[a].add(b)
                graph[b].add(a)
    return graph

def _dsatur_order(conflict_graph):
    """Order class indices from most-conflicting to least.
    Used to seed the initial GA population: harder classes first.

    Note:
        The overall complexity of the DSatur algorithm is O(n^2),
        where n is the number of vertices in the graph.
        https://www.geeksforgeeks.org/dsa/dsatur-algorithm-for-graph-coloring/
    """
    degrees = [len(neighbors) for neighbors in conflict_graph]
    return sorted(range(len(conflict_graph)), key=lambda i: (-degrees[i], i))


def _build_meet_with_exempt_pairs(tt, gc_to_classes):
    """Build the set of class-index pairs exempt from conflict checks.
    A few classes can share a room and instructor at the same time. Or Have no option but to overlap.
    Storage: pairs are stored as (min_idx, max_idx), so a single lookup covers both orderings
        key = (min(ci_a, ci_b), max(ci_a, ci_b))
        if key in pp.meet_with_exempt_pairs:
            continue  # skip -- intentional co-placement
    """
    exempt: set = set()
    for gc_idx, gc in enumerate(tt.group_constraints):
        if gc.type not in ('MEET_WITH', 'CAN_SHARE_ROOM'):
            continue
        class_idxs = gc_to_classes[gc_idx]
        for i in range(len(class_idxs)):
            for j in range(i + 1, len(class_idxs)):
                a, b = class_idxs[i], class_idxs[j]
                exempt.add((min(a, b), max(a, b)))
    return exempt

def preprocess(tt: Timetable) -> PreprocessedData:
    """Build all derived structures
    Note:
        Order matters. gc_indices must be built before conflict_graph and
        meet_with_exempt_pairs because both depend on gc_to_classes.
    """
    time_masks                   = _build_time_masks(tt)
    instructor_to_classes        = _build_instructor_index(tt)
    gc_to_classes, class_to_gcs  = _build_gc_indices(tt)
    conflict_graph               = _build_conflict_graph(tt, instructor_to_classes, gc_to_classes)
    dsatur_order                 = _dsatur_order(conflict_graph)
    meet_with_exempt_pairs        = _build_meet_with_exempt_pairs(tt, gc_to_classes)  # NEW

    return PreprocessedData(
        timetable=tt,
        time_masks=time_masks,
        instructor_to_classes=instructor_to_classes,
        gc_to_classes=gc_to_classes,
        class_to_gcs=class_to_gcs,
        conflict_graph=conflict_graph,
        dsatur_order=dsatur_order,
        meet_with_exempt_pairs=meet_with_exempt_pairs,  # NEW
    )