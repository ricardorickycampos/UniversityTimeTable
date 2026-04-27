"""Flask backend for the UCTP website.

Run from the project root:
    pip install -r server/requirements.txt
    python server/app.py

The server:
  - Serves web/ as static files (http://localhost:5000)
  - Exposes /api/* endpoints for live GA runs, results, and CSV upload
  - Streams GA progress via Server-Sent Events (SSE)
"""
from __future__ import annotations

import io
import json
import queue
import sys
import threading
import time
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

app = Flask(__name__, static_folder=str(ROOT / 'web'), static_url_path='')
CORS(app)

# ── Global run state (one run at a time) ──────────────────────────────────────
_run_queue: queue.Queue = queue.Queue()
_run_lock = threading.Lock()
_run_state: dict = {'running': False, 'phase': None}


# ─────────────────────────────────────────────────────────────────────────────
# Static file serving
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory(str(ROOT / 'web'), 'index.html')


@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory(str(ROOT / 'web'), filename)


# ─────────────────────────────────────────────────────────────────────────────
# API — status & results
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/api/status')
def api_status():
    return jsonify({
        'status': 'ok',
        'mode': 'live',
        'running': _run_state['running'],
        'phase': _run_state.get('phase'),
    })


@app.route('/api/results/list')
def api_list_results():
    rd = ROOT / 'results'
    if not rd.exists():
        return jsonify({'phase1': [], 'phase2_logs': [], 'phase2_assignments': []})
    p1  = sorted(f.name for f in rd.glob('*.json') if not f.name.startswith('phase2_'))
    p2l = sorted(f.name for f in rd.glob('phase2_*log*.json'))
    p2a = sorted(f.name for f in rd.glob('phase2_*assignment*.json'))
    sch = sorted(f.name for f in (ROOT / 'web' / 'results').glob('schedule_*.json'))
    return jsonify({'phase1': p1, 'phase2_logs': p2l, 'phase2_assignments': p2a, 'schedules': sch})


@app.route('/api/results/<path:filename>')
def api_get_result(filename):
    if not filename.endswith('.json'):
        return jsonify({'error': 'Only JSON files served'}), 400

    # Check both results/ and web/results/
    for base in [ROOT / 'results', ROOT / 'web' / 'results']:
        fp = base / filename
        if fp.exists():
            with open(fp) as f:
                return jsonify(json.load(f))
    return jsonify({'error': 'Not found'}), 404


@app.route('/api/schedule/<path:run_id>')
def api_get_schedule(run_id):
    """Return decoded schedule JSON. Generates it on-the-fly if missing."""
    fp = ROOT / 'web' / 'results' / f'schedule_{run_id}.json'
    if not fp.exists():
        try:
            _generate_schedule(run_id)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    if fp.exists():
        with open(fp) as f:
            return jsonify(json.load(f))
    return jsonify({'error': 'Schedule not available — run export_schedule.py first'}), 404


# ─────────────────────────────────────────────────────────────────────────────
# API — run control
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/api/run', methods=['POST'])
def api_start_run():
    if _run_state['running']:
        return jsonify({'error': 'A run is already in progress'}), 409

    data = request.json or {}
    phase         = data.get('phase', 'all')   # 'phase1' | 'phase2' | 'all' | 'quick'
    config_ovr    = data.get('config', {})
    genome_path   = data.get('genome_path', None)

    t = threading.Thread(
        target=_run_thread,
        args=(phase, config_ovr, genome_path),
        daemon=True,
    )
    t.start()
    return jsonify({'status': 'started', 'phase': phase})


@app.route('/api/run/stream')
def api_run_stream():
    """SSE endpoint — client listens for progress messages."""
    def event_gen():
        while True:
            try:
                msg = _run_queue.get(timeout=25)
                yield f'data: {json.dumps(msg)}\n\n'
                if msg.get('type') in ('done', 'error'):
                    break
            except queue.Empty:
                yield f'data: {json.dumps({"type": "ping"})}\n\n'

    return Response(
        event_gen(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


# ─────────────────────────────────────────────────────────────────────────────
# API — CSV upload
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/api/upload/csv', methods=['POST'])
def api_upload_csv():
    from src.io.csv_to_xml import convert_csv_to_xml

    upload_dir = ROOT / 'data' / 'csv_upload'
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved: dict[str, Path] = {}
    for key in ('rooms', 'timeslots', 'sections', 'instructors', 'distances'):
        if key in request.files:
            f = request.files[key]
            dest = upload_dir / f'{key}.csv'
            f.save(dest)
            saved[key] = dest

    required = ['rooms', 'timeslots', 'sections', 'instructors']
    missing = [k for k in required if k not in saved]
    if missing:
        return jsonify({'error': f'Missing required files: {missing}'}), 400

    try:
        xml_path = ROOT / 'data' / 'uploaded_data.xml'
        convert_csv_to_xml(
            rooms_path=saved['rooms'],
            timeslots_path=saved['timeslots'],
            sections_path=saved['sections'],
            instructors_path=saved['instructors'],
            distances_path=saved.get('distances'),
            output_path=xml_path,
        )
        return jsonify({'status': 'converted', 'xml_path': str(xml_path),
                        'message': 'CSV files converted to XML. '
                                   'Update data.input_path in config.yaml to use uploaded_data.xml.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

class _QueueWriter(io.TextIOBase):
    """Redirect print() output to the SSE queue."""
    def __init__(self, q: queue.Queue):
        self._q = q

    def write(self, s: str) -> int:
        if s.strip():
            self._q.put({'type': 'log', 'message': s.rstrip()})
        return len(s)

    def flush(self):
        pass


def _run_thread(phase: str, config_ovr: dict, genome_path: str | None):
    _run_state['running'] = True
    _run_state['phase'] = phase
    old_stdout = sys.stdout
    sys.stdout = _QueueWriter(_run_queue)
    try:
        _execute_run(phase, config_ovr, genome_path)
    except Exception as e:
        _run_queue.put({'type': 'error', 'message': str(e)})
    finally:
        sys.stdout = old_stdout
        _run_state['running'] = False
        _run_state['phase'] = None
        _run_queue.put({'type': 'done'})


def _execute_run(phase: str, config_ovr: dict, genome_path: str | None):
    import yaml
    from src.core.utils import load_config

    cfg_path = ROOT / 'scripts' / 'config.yaml'
    cfg = load_config(cfg_path)

    # Quick-demo preset
    if phase == 'quick':
        phase = 'all'
        cfg['data']['subset'] = config_ovr.get('subset', 100)
        cfg['ga']['population_size'] = 50
        cfg['ga']['n_generations'] = 50
        cfg.setdefault('student_sectioning', {})['sample_size'] = 200
        cfg.setdefault('phase2', {}).setdefault('ga', {})['n_generations'] = 20
    else:
        # Apply caller overrides
        if 'subset' in config_ovr:
            cfg['data']['subset'] = config_ovr['subset']
        if 'sample_size' in config_ovr:
            cfg.setdefault('student_sectioning', {})['sample_size'] = config_ovr['sample_size']
        if 'ga' in config_ovr:
            cfg['ga'].update(config_ovr['ga'])
        if 'phase2' in config_ovr and 'ga' in config_ovr['phase2']:
            cfg.setdefault('phase2', {}).setdefault('ga', {}).update(config_ovr['phase2']['ga'])

    # Write temp config
    tmp_cfg = ROOT / 'scripts' / '_web_run_config.yaml'
    with open(tmp_cfg, 'w') as f:
        yaml.dump(cfg, f)

    p1_log_path = None

    if phase in ('phase1', 'all'):
        from src.scheduling.main import run_phase1
        _run_queue.put({'type': 'phase', 'phase': 'phase1'})
        p1_log_path = run_phase1(tmp_cfg)
        with open(p1_log_path) as f:
            p1_result = json.load(f)
        _run_queue.put({'type': 'phase1_complete', 'result': p1_result})
        genome_path = p1_result['genome_path']

        # Auto-generate schedule JSON
        run_id = Path(p1_log_path).stem
        try:
            _generate_schedule(run_id)
            _run_queue.put({'type': 'schedule_ready', 'run_id': run_id})
        except Exception as e:
            _run_queue.put({'type': 'log', 'message': f'Schedule export skipped: {e}'})

    if phase in ('phase2', 'all'):
        from src.sectioning.main import run_phase2
        gp = Path(genome_path) if genome_path else None
        _run_queue.put({'type': 'phase', 'phase': 'phase2'})
        p2_log_path = run_phase2(tmp_cfg, gp)
        with open(p2_log_path) as f:
            p2_result = json.load(f)
        _run_queue.put({'type': 'phase2_complete', 'result': p2_result})

    if tmp_cfg.exists():
        tmp_cfg.unlink()


def _generate_schedule(run_id: str):
    """Decode a genome .npy and write web/results/schedule_<run_id>.json."""
    from src.core.parser import parse_data
    from src.core.preprocessor import preprocess
    from src.core.utils import load_config
    from src.scheduling.fitness import evaluate_detailed

    DEPT_COLORS = [
        '#3B82F6', '#10B981', '#F59E0B', '#8B5CF6', '#EC4899',
        '#06B6D4', '#EF4444', '#84CC16', '#F97316', '#6366F1',
        '#14B8A6', '#D946EF', '#0EA5E9', '#A3E635', '#FB923C',
    ]

    def _slot_to_time(slot: int) -> str:
        minutes = slot * 5
        h, m = divmod(minutes, 60)
        ampm = 'AM' if h < 12 else 'PM'
        h12 = h if 1 <= h <= 12 else (12 if h in (0, 12) else h - 12)
        return f'{h12}:{m:02d} {ampm}'

    cfg = load_config(ROOT / 'scripts' / 'config.yaml')
    # Infer subset from run_id name
    parts = run_id.split('_')
    size_part = parts[-2] if len(parts) >= 3 else None
    if size_part == 'full':
        this_subset = None
    else:
        try:
            this_subset = int(size_part)
        except (ValueError, TypeError):
            this_subset = cfg['data'].get('subset')

    genome_path = ROOT / 'results' / f'{run_id}_best.npy'
    if not genome_path.exists():
        raise FileNotFoundError(f'Genome not found: {genome_path}')

    genome = np.load(genome_path)
    tt = parse_data(ROOT / cfg['data']['input_path'], subset=this_subset)
    pp = preprocess(tt)
    detail = evaluate_detailed(pp, genome)

    dept_ids = sorted(set(c.department for c in tt.classes))
    dept_color = {d: DEPT_COLORS[i % len(DEPT_COLORS)] for i, d in enumerate(dept_ids)}

    conflict_ci: set[int] = set()
    classes_by_room: dict[int, list[int]] = {}
    for ci, cls in enumerate(tt.classes):
        if not cls.candidate_rooms:
            continue
        rid = cls.candidate_rooms[int(genome[ci, 0])].room_id
        classes_by_room.setdefault(rid, []).append(ci)
    for cidxs in classes_by_room.values():
        for i in range(len(cidxs)):
            for j in range(i + 1, len(cidxs)):
                ci_a, ci_b = cidxs[i], cidxs[j]
                key = (min(ci_a, ci_b), max(ci_a, ci_b))
                if key in pp.meet_with_exempt_pairs:
                    continue
                if np.any(pp.time_masks[ci_a][int(genome[ci_a, 1])] &
                          pp.time_masks[ci_b][int(genome[ci_b, 1])]):
                    conflict_ci.add(ci_a)
                    conflict_ci.add(ci_b)

    classes_out, rooms_out = [], {}
    for ci, cls in enumerate(tt.classes):
        if not cls.candidate_rooms or not cls.candidate_times:
            continue
        rc = cls.candidate_rooms[int(genome[ci, 0])]
        tp = cls.candidate_times[int(genome[ci, 1])]
        room = tt.rooms_by_id[rc.room_id]
        active_days = [d for d in range(7) if tp.days & (1 << d)]
        classes_out.append({
            'class_id': cls.id, 'offering': cls.offering,
            'department': cls.department, 'color': dept_color[cls.department],
            'class_limit': cls.class_limit, 'room_id': room.id, 'room_cap': room.capacity,
            'tp_days': tp.days, 'tp_start': tp.start, 'tp_length': tp.length,
            'start_time': _slot_to_time(tp.start), 'end_time': _slot_to_time(tp.start + tp.length),
            'active_days': active_days, 'instructor_ids': cls.instructor_ids,
            'has_conflict': ci in conflict_ci,
            'n_room_opts': len(cls.candidate_rooms), 'n_time_opts': len(cls.candidate_times),
        })
        rid_str = str(room.id)
        if rid_str not in rooms_out:
            rooms_out[rid_str] = {'id': room.id, 'capacity': room.capacity,
                                  'has_sharing': room.sharing is not None}

    out = {
        'run_id': run_id, 'n_classes': len(classes_out),
        'fitness': float(detail['fitness']), 'hard_total': detail['hard_total'],
        'soft_total': float(detail['soft_total']), 'is_feasible': detail['is_feasible'],
        'hard_breakdown': {k: int(v) if isinstance(v, (int, float)) else v
                           for k, v in detail['hard'].items()},
        'soft_breakdown': {k: float(v) if isinstance(v, (int, float)) else v
                           for k, v in detail['soft'].items()},
        'classes': classes_out, 'rooms': rooms_out,
    }
    out_path = ROOT / 'web' / 'results' / f'schedule_{run_id}.json'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))


# numpy import used inside _generate_schedule — import at module level
try:
    import numpy as np
except ImportError:
    np = None  # type: ignore


if __name__ == '__main__':
    print('UCTP Backend running at http://localhost:5000')
    print('Static files served from web/')
    app.run(debug=True, port=5000, threaded=True)
