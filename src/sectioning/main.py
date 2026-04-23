
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
from src.core.ga import evolve, GAConfig
from src.sectioning.fitness import evaluate, evaluate_detailed
from src.sectioning.sectioner import build_offering_index
from src.sectioning.chromosome import random_chromosome as p2_random_chromosome
import src.sectioning.operators as p2_operators

"""Phase 2 driver: student sectioning.
Reads config.yaml, loads the latest Phase 1 best genome (or one specified
by --genome), runs the Phase 2 GA to find the best student processing
order, saves the final sectioning assignment and statistics.
"""

def find_latest_phase1_genome() -> Path:
    """Find the most recently saved Phase 1 best genome.
    """
    candidates = list(Path('results').glob('run_*_best.npy'))
    if not candidates:
        raise FileNotFoundError(
            'No Phase 1 result found. Run `python -m src.phase1` first.'
        )
    # Sort by modification time (most recent last)
    candidates.sort(key=lambda p: p.stat().st_mtime)
    return candidates[-1]


def build_phase2_ga_config(raw: dict) -> GAConfig:
    """Extract the phase2 section of config and build a GAConfig."""
    p2 = raw.get('phase2', {}).get('ga', {})
    return GAConfig(
        population_size=p2.get('population_size', 30),
        n_generations=p2.get('n_generations', 50),
        crossover_rate=p2.get('crossover_rate', 0.7),
        mutation_rate=p2.get('mutation_rate', 0.001),
        tournament_size=p2.get('tournament_size', 3),
        elitism_count=p2.get('elitism_count', 2),
        hard_weight=1.0,  # not used in Phase 2; fitness is already scalar
        random_seed=p2.get('random_seed', raw.get('ga', {}).get('random_seed', 42)),
        log_every=max(1, p2.get('n_generations', 50) // 25),
    )

def run_phase2(config_path: Path, genome_path: Path = None):
    """Execute a full Phase 2 run. Returns path to the run log JSON."""
    print(f'Loading config from {config_path}...')
    cfg = load_config(config_path)

    # Load Phase 1 result
    if genome_path is None:
        genome_path = find_latest_phase1_genome()
    print(f'Loading Phase 1 genome from {genome_path}...')
    phase1_assignment = np.load(genome_path)
    print(f'  Shape: {phase1_assignment.shape}')

    # Load data
    data_path = Path(cfg['data']['input_path'])
    subset = cfg['data'].get('subset')
    sample_size = cfg.get('student_sectioning', {}).get('sample_size')

    print(f'Parsing {data_path}' + (f' (subset={subset})' if subset else '') + '...')
    tt = parse_data(data_path, subset=subset)
    print(tt.summary())

    # Verify the genome shape matches
    if phase1_assignment.shape[0] != len(tt.classes):
        print(f'ERROR: Phase 1 genome has {phase1_assignment.shape[0]} classes '
              f'but current data has {len(tt.classes)}. Did you change subset?')
        return None

    print('Preprocessing...')
    pp = preprocess(tt)

   # allow testing of different student sample sizes
    all_student_ids = [s.id for s in tt.students]
    if sample_size and sample_size < len(all_student_ids):
        rng_sample = np.random.default_rng(42)
        sampled_indices = rng_sample.choice(
            len(all_student_ids), size=sample_size, replace=False
        )
        sampled_ids = [all_student_ids[i] for i in sampled_indices]
        # Reduce tt.students to only sampled ones.
        tt.students = [tt.students_by_id[sid] for sid in sampled_ids]
        tt.students_by_id = {s.id: s for s in tt.students}
        pp = preprocess(tt)
        print(f'Sampled {sample_size} students for this run')

    n_students = len(tt.students)
    print(f'Phase 2 will section {n_students} students')

    # Build offering index
    offering_index = build_offering_index(pp)
    print(f'Offering index: {len(offering_index)} offerings, '
          f'{sum(len(s) for s in offering_index.values())} subparts')

    # Build fitness closure
    def fitness_fn(genome: np.ndarray) -> float:
        return evaluate(pp, phase1_assignment, genome.tolist(), offering_index)

    ga_cfg = build_phase2_ga_config(cfg)
    print(f'\nPhase 2 GA config: pop={ga_cfg.population_size}, '
          f'gens={ga_cfg.n_generations}, seed={ga_cfg.random_seed}')

    result = evolve(
        pp, fitness_fn, ga_cfg, 
        local_search_fn=None,
        init_pop_fn=_build_p2_init_population(pp, fitness_fn),
        reproduce_fn=p2_operators.reproduce
    )

    # Evaluate final best in detail
    print('\nEvaluating final best order in detail...')
    breakdown = evaluate_detailed(
        pp, phase1_assignment, result.best_genome.tolist(), offering_index,
    )
    print(f'  Fitness:             {breakdown["fitness"]:,.0f}')
    print(f'  Students sectioned:  {breakdown["n_students"]:,}')
    print(f'  Enrollments placed:  {breakdown["enrollments_placed"]:,}')
    print(f'  Enrollments skipped: {breakdown["enrollments_skipped"]:,}')
    print(f'  Coverage:            {breakdown["coverage_pct"]:.2f}%')

    # Save results
    results_dir = Path(cfg['output']['results_dir'])
    results_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = time.strftime('%d%m%y_%H%M')
    size_str = str(sample_size) if sample_size is not None else 'full'
    score_int = int(round(result.best_fitness))

    filename_base = f'phase2_{timestamp}_{size_str}_{score_int}'

    # Save student order
    order_path = results_dir / f'{filename_base}_order.npy'
    np.save(order_path, result.best_genome)

    # Save full sectioning assignment
    assignment_path = results_dir / f'{filename_base}_assignment.json'
    sectioning = breakdown['result']
    assignment_json = {
        str(sid): {str(off): cids for off, cids in offs.items()}
        for sid, offs in sectioning.assignment.items()
    }
    with open(assignment_path, 'w') as f:
        json.dump({
            'timestamp': timestamp,
            'phase1_genome_source': str(genome_path),
            'n_students_processed': sectioning.n_students_processed,
            'n_enrollments_requested': sectioning.n_enrollments_requested,
            'n_enrollments_placed': sectioning.n_enrollments_placed,
            'n_enrollments_skipped': sectioning.n_enrollments_skipped,
            'coverage_pct': breakdown['coverage_pct'],
            'fitness': breakdown['fitness'],
            'section_enrollments': sectioning.final_section_enrollments,
            'assignment': assignment_json,
        }, f, indent=2)

    log_path = results_dir / f'{filename_base}_log.json'
    save_run_log(log_path, {
            'timestamp': timestamp,
            'phase1_genome_source': str(genome_path),
            'config': cfg,
            'total_seconds': result.total_seconds,
            'final_fitness': result.best_fitness,
            'final_breakdown': {
                k: v for k, v in breakdown.items() if k != 'result'
            },
            'history': [asdict(s) for s in result.history],
        })

    print(f'\nSaved:')
    print(f'  Student order:      {order_path}')
    print(f'  Full assignment:    {assignment_path}')
    print(f'  GA history log:     {log_path}')
    return log_path

def _build_p2_init_population(pp, fitness_fn):
    def init_population(pp, size, fitness_fn, rng):
        pop = []
        for _ in range(size):
            g = p2_random_chromosome(pp, rng)
            f = fitness_fn(g)
            pop.append((g, float(f)))
        return pop
    return init_population

def main():
    parser = argparse.ArgumentParser(description='Run Phase 2 student sectioning GA')
    parser.add_argument('--config', type=Path, default=Path('config.yaml'),
                        help='Path to YAML config')
    parser.add_argument('--genome', type=Path, default=None,
                        help='Path to Phase 1 .npy genome (default: latest in results/)')
    args = parser.parse_args()

    if not args.config.exists():
        print(f'Config not found: {args.config}', file=sys.stderr)
        return 1

    run_phase2(args.config, args.genome)
    return 0

if __name__ == '__main__':
    sys.exit(main())
