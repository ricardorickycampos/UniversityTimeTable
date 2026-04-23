
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
import numpy as np
from src.core.utils import load_config, json_default, save_run_log
from src.core.parser import parse_data
from src.core.preprocessor import preprocess
from src.scheduling.fitness import evaluate, evaluate_detailed
from src.core.ga import evolve, GAConfig
from src.scheduling.local_search import make_local_search_fn
import src.scheduling.operators as operators


"""Phase 1 driver: course scheduling."""

def build_ga_config(raw: dict) -> GAConfig:
    """Extract config into a GAConfig dataclass."""
    ga = raw['ga']
    return GAConfig(
        population_size=ga['population_size'],
        n_generations=ga['n_generations'],
        crossover_rate=ga['crossover_rate'],
        mutation_rate=ga['mutation_rate'],
        tournament_size=ga['tournament_size'],
        elitism_count=ga['elitism_count'],
        hard_weight=raw['fitness']['hard_weight'],
        random_seed=ga['random_seed'],
        log_every=max(1, ga['n_generations'] // 50),  # ~50 progress lines total
    )


def run_phase1(config_path: Path) -> Path:
    """Execute a full Phase 1 run. Returns path to the run log JSON."""
    print(f'Loading config from {config_path}...')
    cfg = load_config(config_path)
    data_path = Path(cfg['data']['input_path'])
    subset = cfg['data'].get('subset')
    print(f'Parsing {data_path}' + (f' (subset={subset})' if subset else '') + '...')
    t0 = time.perf_counter()
    tt = parse_data(data_path, subset=subset)
    print(f'  Parsed in {time.perf_counter() - t0:.2f}s')
    print(tt.summary())

    print('Preprocessing...')
    t0 = time.perf_counter()
    pp = preprocess(tt)
    print(f'  Preprocessed in {time.perf_counter() - t0:.2f}s')

    # Build fitness function and GA config
    hard_weight = cfg['fitness']['hard_weight']
    fitness_fn = lambda g: evaluate(pp, g, hard_weight=hard_weight)
    ga_cfg = build_ga_config(cfg)
    print(f'GA config: pop={ga_cfg.population_size}, '
          f'gens={ga_cfg.n_generations}, '
          f'seed={ga_cfg.random_seed}')

    # Build local search (if enabled)
    ls_cfg = cfg['local_search']
    if ls_cfg['enabled']:
        print(f'Memetic step ENABLED: top_k={ls_cfg["top_k"]}, '
              f'max_passes={ls_cfg["max_passes"]}, '
              f'every {ls_cfg["apply_every_n_gens"]} gens')
        ls_rng = np.random.default_rng(ga_cfg.random_seed + 1000)
        local_search_fn = make_local_search_fn(
            pp=pp,
            fitness_fn=fitness_fn,
            rng=ls_rng,
            max_passes=ls_cfg['max_passes'],
        )
        apply_every = ls_cfg.get('apply_every_n_gens', 1)
        if apply_every > 1:
            print("Local Search Started...")
            local_search_fn = _throttled(local_search_fn, 
                                         apply_every,
                                         calls_per_gen=cfg['ga']['elitism_count'],
                                         )
    else:
        print('Memetic step DISABLED')
        local_search_fn = None

    # Run evolution
    print('\n' + '=' * 60)
    print('Starting evolution')
    print('=' * 60)
    result = evolve(
        pp, fitness_fn, ga_cfg, 
        local_search_fn=local_search_fn,
        init_pop_fn=operators.init_population,
        reproduce_fn=operators.reproduce
    )

    # Evaluate the final best in detail (for the log)

    print('\nEvaluating final best in detail...')
    final_breakdown = evaluate_detailed(pp, result.best_genome, hard_weight=hard_weight)
    print(f'  Fitness:     {final_breakdown["fitness"]:.1f}')
    print(f'  Hard total:  {final_breakdown["hard_total"]}')
    print(f'  Soft total:  {final_breakdown["soft_total"]:.1f}')
    print(f'  Feasible:    {final_breakdown["is_feasible"]}')

    # Save results

    results_dir = Path(cfg['output']['results_dir'])
    results_dir.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime('%d%m%y_%H%M')
    size_str = str(subset) if subset is not None else 'full'
    score_int = int(round(result.best_fitness))

    filename_base = f'run_{timestamp}_{size_str}_{score_int}'
    log_path = results_dir / f'{filename_base}.json'
    genome_path = results_dir / f'{filename_base}_best.npy'

    np.save(genome_path, result.best_genome)
    print(f'\nBest genome saved to {genome_path}')

    run_log = {
        'timestamp': timestamp,
        'config_path': str(config_path),
        'config': cfg,
        'data_summary': {
            'n_classes': len(tt.classes),
            'n_rooms': len(tt.rooms),
            'n_students': len(tt.students),
            'n_group_constraints': len(tt.group_constraints),
        },
        'total_seconds': result.total_seconds,
        'stopped_early': result.stopped_early,
        'final_fitness': result.best_fitness,
        'final_breakdown': final_breakdown,
        'genome_path': str(genome_path),
        'history': [asdict(s) for s in result.history],
    }

    save_run_log(log_path, run_log)
    print(f'Run log saved to {log_path}')

    return log_path


def _throttled(fn, every: int, calls_per_gen: int = 1):
    """Wrap a local-search function so it only fires every Nth call.
    """
    call_count = [0]

    def _wrapped(genome: np.ndarray, fitness: float):
        call_count[0] += 1
        if call_count[0] % (every * calls_per_gen) != 0:
            return genome, fitness
        return fn(genome, fitness)
    return _wrapped


def main():
    parser = argparse.ArgumentParser(description='Run Phase 1 GA')
    parser.add_argument(
        '--config',
        type=Path,
        default=Path('scripts/config.yaml'),
        help='Path to YAML config (default: config.yaml)',
    )
    args = parser.parse_args()

    if not args.config.exists():
        print(f'Config not found: {args.config}', file=sys.stderr)
        return 1

    run_phase1(args.config)
    return 0


if __name__ == '__main__':
    sys.exit(main())