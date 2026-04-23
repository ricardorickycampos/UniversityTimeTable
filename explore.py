"""
Notebook exploration module for the timetabling GA.
from explore import load, phase1, phase2
    # Load everything once
    ctx = load() # uses latest .npy in results/
    ctx = load('results/run_xyz_best.npy')

    # Phase 1 views
    phase1.schedule(ctx) # full class DataFrame
    phase1.violations(ctx) # constraint breakdown
    phase1.over_capacity(ctx) # only over-cap rows
    phase1.room_usage(ctx) # how packed each room is
    phase1.department(ctx, dept_id) # one department's classes

    # Phase 2 views (only if ctx has a phase2 assignment loaded)
    ctx2 = load('results/run_xyz_best.npy', 'results/phase2_xyz_assignment.json')
    phase2.summary(ctx2) # coverage, skips, conflicts
    phase2.student(ctx2, student_id) # one student's full schedule
    phase2.section_load(ctx2) # enrollment count per section
    phase2.skipped(ctx2) # students with missed enrollments
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd

def _get_pipeline():
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from src.core.parser import parse_data
    from src.core.preprocessor import preprocess
    from src.scheduling.fitness import evaluate_detailed as p1_evaluate
    return parse_data, preprocess, p1_evaluate


class Context:
    def __init__(self, genome, pp, p1_detail, p2_data=None):
        self.genome   = genome        # np.ndarray (n_classes, 2)
        self.pp       = pp
        self.tt       = pp.timetable
        self.detail   = p1_detail     # dict from evaluate_detailed
        self.p2       = p2_data       # dict from phase2 assignment JSON, or None

    def __repr__(self):
        n = len(self.tt.classes)
        feasible = self.detail['is_feasible']
        fitness  = self.detail['fitness']
        p2_str   = f", phase2={self.p2 is not None}" if self.p2 else ""
        return f"<Context classes={n} fitness={fitness:.0f} feasible={feasible}{p2_str}>"

def load(
    genome_path: Optional[str | Path] = None,
    p2_assignment_path: Optional[str | Path] = None,
    data_path: str | Path = 'data/data.xml',
    subset: Optional[int] = None,
    config_path: Optional[str | Path] = 'scripts/config.yaml',
) -> Context:

    parse_data, preprocess, p1_evaluate = _get_pipeline()

    if config_path and Path(config_path).exists():
        import yaml
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        data_path = cfg['data']['input_path']
        if subset is None:
            subset = cfg['data'].get('subset')

    if genome_path is None:
        candidates = sorted(Path('results').glob('run_*_best.npy'),
                            key=lambda p: p.stat().st_mtime)
        if not candidates:
            raise FileNotFoundError("No Phase 1 .npy found in results/. Pass genome_path explicitly.")
        genome_path = candidates[-1]
        print(f"Auto-selected genome: {genome_path}")

    genome = np.load(genome_path)
    print(f"Genome shape: {genome.shape}")

    print(f"Parsing {data_path}" + (f" (subset={subset})" if subset else "") + "...")
    tt = parse_data(data_path, subset=subset)
    pp = preprocess(tt)

    print("Evaluating constraints...")
    detail = p1_evaluate(pp, genome)

    p2_data = None
    if p2_assignment_path:
        with open(p2_assignment_path) as f:
            p2_data = json.load(f)
        print(f"Phase 2 assignment loaded: {p2_data.get('n_students_processed', '?')} students")

    ctx = Context(genome, pp, detail, p2_data)
    print(ctx)
    return ctx

class _Phase1:
    def schedule(self, ctx: Context) -> pd.DataFrame:
        """Full schedule — one row per class with decoded room + time."""
        tt = ctx.tt
        rows = []
        for i, cls in enumerate(tt.classes):
            room_idx, time_idx = int(ctx.genome[i, 0]), int(ctx.genome[i, 1])
            room_cand = cls.candidate_rooms[room_idx] if cls.candidate_rooms else None
            room      = tt.rooms_by_id[room_cand.room_id] if room_cand else None
            tp        = cls.candidate_times[time_idx] if cls.candidate_times else None
            rows.append({
                'class_id':    cls.id,
                'offering':    cls.offering,
                'department':  cls.department,
                'limit':       cls.class_limit,
                'room_id':     room.id if room else None,
                'room_cap':    room.capacity if room else None,
                'over_cap':    max(0, cls.class_limit - room.capacity) if room else 0,
                'room_pref':   room_cand.pref if room_cand else None,
                'time_pref':   tp.pref if tp else None,
                'days':        bin(tp.days) if tp else None,
                'start':       tp.start if tp else None,
                'length':      tp.length if tp else None,
                'n_rooms':     len(cls.candidate_rooms),
                'n_times':     len(cls.candidate_times),
            })
        return pd.DataFrame(rows)

    def violations(self, ctx: Context) -> pd.DataFrame:
        """Flat constraint breakdown as a two-column DataFrame."""
        d = ctx.detail
        rows = (
            [('HARD', k, v) for k, v in d['hard'].items() if k != 'total'] +
            [('SOFT', k, round(v, 1)) for k, v in d['soft'].items() if k != 'total']
        )
        df = pd.DataFrame(rows, columns=['kind', 'constraint', 'value'])
        df.loc[len(df)] = ['—', 'fitness', round(d['fitness'], 1)]
        df.loc[len(df)] = ['—', 'feasible', d['is_feasible']]
        return df

    def over_capacity(self, ctx: Context) -> pd.DataFrame:
        """Only the classes where enrollment limit exceeds room capacity."""
        df = self.schedule(ctx)
        return df[df['over_cap'] > 0].reset_index(drop=True)

    def room_usage(self, ctx: Context) -> pd.DataFrame:
        """One row per room: how many classes, total enrollment, capacity utilisation."""
        df = self.schedule(ctx)
        g = df.groupby('room_id').agg(
            n_classes=('class_id', 'count'),
            total_enrolled=('limit', 'sum'),
            room_cap=('room_cap', 'first'),
        ).reset_index()
        g['utilisation_pct'] = (g['total_enrolled'] / g['room_cap'] * 100).round(1)
        return g.sort_values('utilisation_pct', ascending=False).reset_index(drop=True)

    def department(self, ctx: Context, dept_id: int) -> pd.DataFrame:
        """All classes belonging to one department."""
        df = self.schedule(ctx)
        return df[df['department'] == dept_id].reset_index(drop=True)

class _Phase2:

    def _require(self, ctx: Context):
        if ctx.p2 is None:
            raise ValueError("No Phase 2 data loaded. Pass p2_assignment_path to load().")

    def summary(self, ctx: Context) -> pd.DataFrame:
        """Top-level Phase 2 stats as a single-column DataFrame."""
        self._require(ctx)
        p2 = ctx.p2
        rows = {
            'students_processed':    p2['n_students_processed'],
            'enrollments_requested': p2['n_enrollments_requested'],
            'enrollments_placed':    p2['n_enrollments_placed'],
            'enrollments_skipped':   p2['n_enrollments_skipped'],
            'coverage_pct':          round(p2['coverage_pct'], 2),
            'fitness':               round(p2['fitness'], 1),
        }
        return pd.DataFrame(rows.items(), columns=['metric', 'value'])

    def student(self, ctx: Context, student_id: int) -> pd.DataFrame:
        """All section assignments for one student."""
        self._require(ctx)
        assignment = ctx.p2['assignment'].get(str(student_id))
        if assignment is None:
            print(f"Student {student_id} has no assignment (not processed or fully skipped).")
            return pd.DataFrame()
        tt = ctx.tt
        rows = []
        for offering_id, class_ids in assignment.items():
            for class_id in class_ids:
                cls = tt.classes_by_id.get(int(class_id))
                if cls is None:
                    continue
                time_idx = int(ctx.genome[tt.classes.index(cls), 1])
                tp = cls.candidate_times[time_idx] if cls.candidate_times else None
                rows.append({
                    'offering':   int(offering_id),
                    'class_id':   int(class_id),
                    'subpart':    cls.subpart,
                    'department': cls.department,
                    'days':       bin(tp.days) if tp else None,
                    'start':      tp.start if tp else None,
                    'length':     tp.length if tp else None,
                })
        return pd.DataFrame(rows)

    def section_load(self, ctx: Context) -> pd.DataFrame:
        """Enrollment count vs capacity for every section."""
        self._require(ctx)
        tt = ctx.tt
        se = ctx.p2['section_enrollments']
        rows = []
        for cls in tt.classes:
            enrolled = se.get(str(cls.id), se.get(cls.id, 0))
            rows.append({
                'class_id':  cls.id,
                'offering':  cls.offering,
                'subpart':   cls.subpart,
                'limit':     cls.class_limit,
                'enrolled':  enrolled,
                'remaining': cls.class_limit - enrolled,
                'full':      enrolled >= cls.class_limit,
            })
        df = pd.DataFrame(rows)
        return df.sort_values('enrolled', ascending=False).reset_index(drop=True)

    def skipped(self, ctx: Context) -> pd.DataFrame:
        """Students who have at least one skipped enrollment."""
        self._require(ctx)
        tt = ctx.tt
        assignment = ctx.p2['assignment']
        placed_counts = {
            int(sid): sum(len(v) for v in offs.values())
            for sid, offs in assignment.items()
        }
        rows = []
        for student in tt.students:
            placed   = placed_counts.get(student.id, 0)
            requested = len(student.enrollments)
            skipped  = requested - placed
            if skipped > 0:
                rows.append({
                    'student_id': student.id,
                    'requested':  requested,
                    'placed':     placed,
                    'skipped':    skipped,
                })
        return pd.DataFrame(rows).sort_values('skipped', ascending=False).reset_index(drop=True)

phase1 = _Phase1()
phase2 = _Phase2()