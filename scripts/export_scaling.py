"""Generate web/results/scaling.json by running a short GA at multiple subset sizes.

WARNING: Takes 5–30 minutes depending on hardware. Run once from the project root:
    python scripts/export_scaling.py

Writes web/results/scaling.json with runtime, fitness, and feasibility per subset size.
Commit the result to enable the Scaling Analysis chart on GitHub Pages.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml

WEB_RESULTS = ROOT / 'web' / 'results'

# Subset sizes (number of classes) to benchmark
SUBSETS = [50, 100, 200, 400, 896]

# Short GA settings — fast enough to show scaling without hours of runtime
SCALING_GA = {
    'population_size': 30,
    'n_generations':   50,
    'crossover_rate':  0.7,
    'mutation_rate':   0.002,
    'tournament_size': 3,
    'elitism_count':   2,
    'random_seed':     42,
}


def run_at_subset(base_cfg: dict, subset: int | None) -> dict:
    from src.scheduling.main import run_phase1

    cfg = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base_cfg.items()}
    cfg.setdefault('data', {})['subset'] = subset
    cfg['ga'] = {**cfg.get('ga', {}), **SCALING_GA}

    tmp = ROOT / 'scripts' / '_scaling_run.yaml'
    with open(tmp, 'w') as f:
        yaml.dump(cfg, f)

    t0 = time.time()
    log_path = run_phase1(str(tmp))
    runtime = round(time.time() - t0, 2)

    tmp.unlink(missing_ok=True)

    with open(log_path) as f:
        log = json.load(f)

    ds = log.get('data_summary', {})
    fb = log.get('final_breakdown') or {}
    hard = fb.get('hard', {}) if isinstance(fb.get('hard'), dict) else {}

    return {
        'subset':          subset or 896,
        'n_classes':       ds.get('n_classes', subset or 896),
        'runtime_s':       runtime,
        'fitness':         round(float(log.get('final_fitness', 0)), 1),
        'hard_violations': int(hard.get('total', 0)),
        'is_feasible':     int(hard.get('total', 1)) == 0,
        'n_generations':   len(log.get('history', [])),
    }


def main():
    WEB_RESULTS.mkdir(parents=True, exist_ok=True)

    from src.core.utils import load_config
    base_cfg = load_config(ROOT / 'scripts' / 'config.yaml')

    print('Scaling analysis — running short GA at multiple subset sizes')
    print(f'Settings: pop={SCALING_GA["population_size"]}, '
          f'gen={SCALING_GA["n_generations"]}, seed={SCALING_GA["random_seed"]}\n')

    runs = []
    for subset in SUBSETS:
        label = f'subset={subset}' if subset < 896 else 'full (896 classes)'
        print(f'  Running {label}...', end=' ', flush=True)
        try:
            r = run_at_subset(base_cfg, subset if subset < 896 else None)
            runs.append(r)
            print(f'done  {r["runtime_s"]}s  '
                  f'fitness={r["fitness"]}  '
                  f'hard={r["hard_violations"]}  '
                  f'feasible={r["is_feasible"]}')
        except Exception as e:
            print(f'FAILED: {e}')

    out = {'ga_settings': SCALING_GA, 'runs': runs}
    (WEB_RESULTS / 'scaling.json').write_text(json.dumps(out, indent=2))
    print(f'\nWrote web/results/scaling.json  ({len(runs)} data points)')
    print('Commit this file so GitHub Pages shows the Scaling Analysis chart.')


if __name__ == '__main__':
    main()
