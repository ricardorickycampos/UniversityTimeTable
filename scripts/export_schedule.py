"""Export decoded schedule JSON files for static website viewing.

Reads every results/run_*_best.npy genome + data/data.xml and writes
  web/results/schedule_<run_id>.json   — decoded class assignments
  web/results/manifest.json            — index of all available result files

Run once from the project root before deploying to GitHub Pages:
    python scripts/export_schedule.py

The GitHub Actions workflow also runs this automatically on push.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np

from src.core.parser import parse_data
from src.core.preprocessor import preprocess
from src.core.utils import load_config
from src.scheduling.fitness import evaluate_detailed

DEPT_COLORS = [
    '#3B82F6', '#10B981', '#F59E0B', '#8B5CF6', '#EC4899',
    '#06B6D4', '#EF4444', '#84CC16', '#F97316', '#6366F1',
    '#14B8A6', '#D946EF', '#0EA5E9', '#A3E635', '#FB923C',
]

WEB_RESULTS = ROOT / 'web' / 'results'
RESULTS_DIR = ROOT / 'results'


def slot_to_time(slot: int) -> str:
    minutes = slot * 5
    h, m = divmod(minutes, 60)
    ampm = 'AM' if h < 12 else 'PM'
    h12 = h if 1 <= h <= 12 else (12 if h == 0 or h == 12 else h - 12)
    return f'{h12}:{m:02d} {ampm}'


def export_one(genome_path: Path, tt, pp, run_id: str) -> dict:
    """Decode a genome and write schedule_<run_id>.json. Returns summary dict."""
    genome = np.load(genome_path)

    if genome.shape[0] != len(tt.classes):
        print(f'  SKIP {run_id}: genome size {genome.shape[0]} != {len(tt.classes)} classes')
        return {}

    detail = evaluate_detailed(pp, genome)

    # Build conflict set
    conflict_ci: set[int] = set()
    classes_by_room: dict[int, list[int]] = {}
    for ci, cls in enumerate(tt.classes):
        if not cls.candidate_rooms:
            continue
        rid = cls.candidate_rooms[int(genome[ci, 0])].room_id
        classes_by_room.setdefault(rid, []).append(ci)

    for rid, cidxs in classes_by_room.items():
        for i in range(len(cidxs)):
            for j in range(i + 1, len(cidxs)):
                ci_a, ci_b = cidxs[i], cidxs[j]
                key = (min(ci_a, ci_b), max(ci_a, ci_b))
                if key in pp.meet_with_exempt_pairs:
                    continue
                ma = pp.time_masks[ci_a][int(genome[ci_a, 1])]
                mb = pp.time_masks[ci_b][int(genome[ci_b, 1])]
                if np.any(ma & mb):
                    conflict_ci.add(ci_a)
                    conflict_ci.add(ci_b)

    # Department color map
    dept_ids = sorted(set(c.department for c in tt.classes))
    dept_color = {d: DEPT_COLORS[i % len(DEPT_COLORS)] for i, d in enumerate(dept_ids)}

    # Build classes list
    classes_out = []
    rooms_out: dict[str, dict] = {}
    for ci, cls in enumerate(tt.classes):
        if not cls.candidate_rooms or not cls.candidate_times:
            continue
        room_idx = int(genome[ci, 0])
        time_idx = int(genome[ci, 1])
        rc = cls.candidate_rooms[room_idx]
        tp = cls.candidate_times[time_idx]
        room = tt.rooms_by_id[rc.room_id]

        active_days = [d for d in range(7) if tp.days & (1 << d)]

        classes_out.append({
            'class_id':    cls.id,
            'offering':    cls.offering,
            'department':  cls.department,
            'color':       dept_color[cls.department],
            'class_limit': cls.class_limit,
            'room_id':     room.id,
            'room_cap':    room.capacity,
            'tp_days':     tp.days,
            'tp_start':    tp.start,
            'tp_length':   tp.length,
            'start_time':  slot_to_time(tp.start),
            'end_time':    slot_to_time(tp.start + tp.length),
            'active_days': active_days,
            'instructor_ids': cls.instructor_ids,
            'has_conflict':   ci in conflict_ci,
            'n_room_opts': len(cls.candidate_rooms),
            'n_time_opts': len(cls.candidate_times),
        })

        rid_str = str(room.id)
        if rid_str not in rooms_out:
            rooms_out[rid_str] = {
                'id': room.id,
                'capacity': room.capacity,
                'has_sharing': room.sharing is not None,
            }

    out = {
        'run_id':         run_id,
        'n_classes':      len(classes_out),
        'fitness':        float(detail['fitness']),
        'hard_total':     detail['hard_total'],
        'soft_total':     float(detail['soft_total']),
        'is_feasible':    detail['is_feasible'],
        'hard_breakdown': {k: int(v) if isinstance(v, (int, float)) else v
                           for k, v in detail['hard'].items()},
        'soft_breakdown': {k: float(v) if isinstance(v, (int, float)) else v
                           for k, v in detail['soft'].items()},
        'classes': classes_out,
        'rooms':   rooms_out,
    }

    out_path = WEB_RESULTS / f'schedule_{run_id}.json'
    out_path.write_text(json.dumps(out, indent=2))
    print(f'  Wrote {out_path.name}  ({len(classes_out)} classes, '
          f'fitness={out["fitness"]:.0f}, feasible={out["is_feasible"]})')
    return out


def export_analysis(
    genome_path: Path,
    tt,
    pp,
    run_id: str,
    p2_path: Path | None = None,
) -> bool:
    """Write analysis_<run_id>.json: room usage, violations, over-capacity, phase2 stats."""
    genome = np.load(genome_path)
    if genome.shape[0] != len(tt.classes):
        print(f'  SKIP analysis {run_id}: genome size mismatch')
        return False

    detail = evaluate_detailed(pp, genome)

    # Room usage — track n_classes and total_enrolled per room
    room_data: dict[int, dict] = {}
    for ci, cls in enumerate(tt.classes):
        if not cls.candidate_rooms:
            continue
        rid = cls.candidate_rooms[int(genome[ci, 0])].room_id
        room = tt.rooms_by_id[rid]
        if rid not in room_data:
            room_data[rid] = {
                'room_id': rid, 'room_cap': room.capacity,
                'n_classes': 0, 'total_enrolled': 0,
            }
        room_data[rid]['n_classes'] += 1
        room_data[rid]['total_enrolled'] += cls.class_limit

    room_usage = []
    for rd in room_data.values():
        n, cap = rd['n_classes'], rd['room_cap']
        avg_fill = round((rd['total_enrolled'] / n) / cap * 100, 1) if cap and n else 0.0
        room_usage.append({**rd, 'avg_fill_pct': avg_fill})
    room_usage.sort(key=lambda x: -x['avg_fill_pct'])

    # Over-capacity classes
    over_capacity = []
    for ci, cls in enumerate(tt.classes):
        if not cls.candidate_rooms:
            continue
        rid = cls.candidate_rooms[int(genome[ci, 0])].room_id
        room = tt.rooms_by_id[rid]
        over = cls.class_limit - room.capacity
        if over > 0:
            over_capacity.append({
                'class_id': cls.id, 'department': cls.department,
                'limit': cls.class_limit, 'room_id': room.id,
                'room_cap': room.capacity, 'over_cap': over,
            })
    over_capacity.sort(key=lambda x: -x['over_cap'])

    out: dict = {
        'run_id': run_id,
        'violations': {
            'hard': {k: int(v) if isinstance(v, (int, float)) else v
                     for k, v in detail['hard'].items()},
            'soft': {k: round(float(v), 2) if isinstance(v, (int, float)) else v
                     for k, v in detail['soft'].items()},
            'fitness': float(detail['fitness']),
            'is_feasible': bool(detail['is_feasible']),
        },
        'room_usage': room_usage[:30],
        'over_capacity': over_capacity,
        'phase2': None,
    }

    if p2_path and p2_path.exists():
        with open(p2_path) as f:
            p2 = json.load(f)

        se = p2.get('section_enrollments', {})
        section_load = []
        for cls in tt.classes:
            enrolled = int(se.get(str(cls.id), se.get(cls.id, 0)))
            fill_pct = round(enrolled / cls.class_limit * 100, 1) if cls.class_limit else 0.0
            section_load.append({
                'class_id': cls.id, 'offering': cls.offering,
                'enrolled': enrolled, 'limit': cls.class_limit, 'fill_pct': fill_pct,
            })
        section_load.sort(key=lambda x: -x['enrolled'])

        fill_dist = {'empty': 0, 'under_50': 0, 'f50_75': 0, 'f75_99': 0, 'full': 0}
        for s in section_load:
            if s['enrolled'] == 0:
                fill_dist['empty'] += 1
            elif s['fill_pct'] < 50:
                fill_dist['under_50'] += 1
            elif s['fill_pct'] < 75:
                fill_dist['f50_75'] += 1
            elif s['fill_pct'] < 100:
                fill_dist['f75_99'] += 1
            else:
                fill_dist['full'] += 1

        fb = p2.get('final_breakdown') or {}
        out['phase2'] = {
            'n_students':          p2.get('n_students_processed') or fb.get('n_students'),
            'coverage_pct':        p2.get('coverage_pct')         or fb.get('coverage_pct'),
            'enrollments_placed':  p2.get('n_enrollments_placed') or fb.get('enrollments_placed'),
            'enrollments_skipped': p2.get('n_enrollments_skipped')or fb.get('enrollments_skipped'),
            'section_load':        section_load[:20],
            'fill_distribution':   fill_dist,
        }

    out_path = WEB_RESULTS / f'analysis_{run_id}.json'
    out_path.write_text(json.dumps(out, indent=2))
    print(f'  Wrote {out_path.name}  '
          f'(rooms={len(room_usage)}, overcap={len(over_capacity)}, '
          f'phase2={"yes" if out["phase2"] else "no"})')
    return True


def build_manifest(
    p1_logs: list[str],
    p2_logs: list[str],
    p2_assignments: list[str],
    schedules: list[str],
    analyses: list[str] | None = None,
) -> None:
    manifest = {
        'phase1':             sorted(p1_logs),
        'phase2_logs':        sorted(p2_logs),
        'phase2_assignments': sorted(p2_assignments),
        'schedules':          sorted(schedules),
        'analyses':           sorted(analyses or []),
    }
    path = WEB_RESULTS / 'manifest.json'
    path.write_text(json.dumps(manifest, indent=2))
    print(f'Wrote manifest.json ({len(p1_logs)} phase1, {len(schedules)} schedules, '
          f'{len(analyses or [])} analyses)')


def main():
    WEB_RESULTS.mkdir(parents=True, exist_ok=True)

    # Load config to get subset setting
    cfg_path = ROOT / 'scripts' / 'config.yaml'
    cfg = load_config(cfg_path)

    # Copy all result JSON files to web/results/
    print('Copying result JSON files...')
    p1_logs, p2_logs, p2_assignments = [], [], []
    for src in RESULTS_DIR.glob('*.json'):
        dst = WEB_RESULTS / src.name
        dst.write_text(src.read_text())
        if src.name.startswith('phase2_') and 'log' in src.name:
            p2_logs.append(src.name)
        elif src.name.startswith('phase2_') and 'assignment' in src.name:
            p2_assignments.append(src.name)
        elif not src.name.startswith('phase2_'):
            p1_logs.append(src.name)
        print(f'  Copied {src.name}')

    # Export schedule JSON for each phase1 genome (*_best.npy)
    print('\nExporting schedule JSONs...')
    data_path = ROOT / cfg['data']['input_path']

    genome_files = sorted(RESULTS_DIR.glob('*_best.npy'))
    if not genome_files:
        print('  No *_best.npy genome files found in results/. Skipping schedule export.')
        build_manifest(p1_logs, p2_logs, p2_assignments, [], [])
        return

    # Cache loaded timetable by subset to avoid reloading per genome
    loaded: dict[int | None, tuple] = {}

    # Find latest phase2 assignment for cross-referencing in analysis
    p2_asgn_candidates = sorted(RESULTS_DIR.glob('phase2_*assignment*.json'),
                                key=lambda p: p.stat().st_mtime)
    p2_asgn_path = p2_asgn_candidates[-1] if p2_asgn_candidates else None

    schedules: list[str] = []
    analyses:  list[str] = []

    for gf in genome_files:
        # run_id = full stem of the .npy file (e.g. "phase1_6000_best")
        run_id = gf.stem
        # Infer subset: look for "full" token or a pure-integer token in the stem
        parts = gf.stem.split('_')
        this_subset = None
        for part in parts:
            if part == 'full':
                this_subset = None
                break
            try:
                v = int(part)
                if 10 <= v <= 10000:   # plausible subset size
                    this_subset = v
            except ValueError:
                pass

        if this_subset not in loaded:
            print(f'  Loading data (subset={this_subset})...')
            tt = parse_data(data_path, subset=this_subset)
            pp = preprocess(tt)
            loaded[this_subset] = (tt, pp)

        tt, pp = loaded[this_subset]
        result = export_one(gf, tt, pp, run_id)
        if result:
            schedules.append(f'schedule_{run_id}.json')

        if export_analysis(gf, tt, pp, run_id, p2_asgn_path):
            analyses.append(f'analysis_{run_id}.json')

    build_manifest(p1_logs, p2_logs, p2_assignments, schedules, analyses)
    print('\nDone. Commit the web/results/ folder to enable static mode on GitHub Pages.')


if __name__ == '__main__':
    main()
