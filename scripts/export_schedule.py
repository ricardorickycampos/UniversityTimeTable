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


def build_manifest(
    p1_logs: list[str],
    p2_logs: list[str],
    p2_assignments: list[str],
    schedules: list[str],
) -> None:
    manifest = {
        'phase1':          sorted(p1_logs),
        'phase2_logs':     sorted(p2_logs),
        'phase2_assignments': sorted(p2_assignments),
        'schedules':       sorted(schedules),
    }
    path = WEB_RESULTS / 'manifest.json'
    path.write_text(json.dumps(manifest, indent=2))
    print(f'Wrote manifest.json ({len(p1_logs)} phase1, {len(p2_logs)} phase2 runs)')


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
        build_manifest(p1_logs, p2_logs, p2_assignments, [])
        return

    # Cache loaded timetable by subset to avoid reloading per genome
    loaded: dict[int | None, tuple] = {}

    schedules = []
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

    build_manifest(p1_logs, p2_logs, p2_assignments, schedules)
    print('\nDone. Commit the web/results/ folder to enable static mode on GitHub Pages.')


if __name__ == '__main__':
    main()
