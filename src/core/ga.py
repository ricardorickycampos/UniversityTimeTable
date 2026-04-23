"""Main genetic algorithm evolution loop.
All logic is injected via the fitness_fn
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Callable, Optional
import numpy as np
from src.core.preprocessor import PreprocessedData


# ============ Configuration and result types ===============

@dataclass
class GAConfig:
    """
    Populated by the phase driver from config.yaml.
    Default values reflected in code
    """
    population_size: int = 100
    n_generations: int = 500
    crossover_rate: float = 0.7 # odds of crossover
    mutation_rate: float = 0.001 # probability of mutation per gene
    tournament_size: int = 3
    elitism_count: int = 2
    hard_weight: float = 1000.0
    random_seed: int = 42
    log_every: int = 10 # print progress every N generations
    early_stopping_patience: Optional[int] = None  # None = no early stop


@dataclass
class GenerationStats:
    """Stats for a single generation. """
    generation: int
    best_fitness: float
    avg_fitness: float
    worst_fitness: float
    elapsed_seconds: float

@dataclass
class EvolveResult:
    """Best individual plus full history."""
    best_genome: np.ndarray
    best_fitness: float
    history: list = field(default_factory=list)  # list[GenerationStats]
    total_seconds: float = 0.0
    stopped_early: bool = False


# ========== Standard GA Operators ==========
def tournament_select(population: list, k: int, rng: np.random.Generator) -> np.ndarray:
    """ Returns best individuals of size k from the population. (lowest fitness)"""
    indices = rng.integers(len(population), size=k)
    best_idx = min(indices, key=lambda i: population[i][1])
    return population[best_idx][0]


def get_elites(population: list, n_elites: int) -> list:
    """ Returns top n elites from the population."""
    sorted_pop = sorted(population, key=lambda x: x[1])
    return [(g.copy(), f) for g, f in sorted_pop[:n_elites]]

# ========== Main evolve loop ==========

def evolve(
    pp: PreprocessedData,
    fitness_fn: Callable[[np.ndarray], float],
    config: GAConfig,
    local_search_fn: Optional[Callable[[np.ndarray, float], tuple]] = None,
    init_pop_fn: Optional[Callable] = None,
    reproduce_fn: Optional[Callable] = None,
) -> EvolveResult:
    """GA evolution.
    Args -
        @pp: Preprocessed data (needed by operators).
        @fitness_fn: genome -> float. Closure over pp & hard_weight.
        @config: GAConfig instance.
        @local_search_fn: Optional (genome, fitness), function for the memetic step. None disables.
        @init_pop_fn: Optional function to initialize population.
        @reproduce_fn: Optional function to produce offspring.

    Returns: EvolveResult with best_genome, best_fitness, and a history list.
    """
    # Use provided operators or raise an error if missing
    if init_pop_fn is None:
        raise ValueError("init_pop_fn must be provided to evolve()")
    if reproduce_fn is None:
        raise ValueError("reproduce_fn must be provided to evolve()")

    rng = np.random.default_rng(config.random_seed)
    start_time = time.perf_counter()

    # Step 1: initialize
    print(f'Initializing population of {config.population_size}...')
    population = init_pop_fn(
        pp=pp,
        size=config.population_size,
        fitness_fn=fitness_fn,
        rng=rng,
    )
    best_genome, best_fitness = min(population, key=lambda x: x[1])
    best_genome = best_genome.copy()

    history: list = []
    stagnation_counter = 0
    stopped_early = False

    # Main loop
    for gen in range(config.n_generations):
        gen_start = time.perf_counter()

        fitnesses = [f for _, f in population]
        stats = GenerationStats(
            generation=gen,
            best_fitness=min(fitnesses),
            avg_fitness=float(np.mean(fitnesses)),
            worst_fitness=max(fitnesses),
            elapsed_seconds=time.perf_counter() - start_time,
        )
        history.append(stats)

        if gen % config.log_every == 0 or gen == config.n_generations - 1:
            print(f'  gen {gen:4d}: best={stats.best_fitness:>10.1f}  '
                  f'avg={stats.avg_fitness:>10.1f}  '
                  f'worst={stats.worst_fitness:>10.1f}  '
                  f'elapsed={stats.elapsed_seconds:.1f}s')

        gen_best_genome, gen_best_fit = min(population, key=lambda x: x[1])
        if gen_best_fit < best_fitness:
            best_genome = gen_best_genome.copy()
            best_fitness = gen_best_fit
            stagnation_counter = 0
        else:
            stagnation_counter += 1

        # Early stopping check
        if (config.early_stopping_patience is not None and
                stagnation_counter >= config.early_stopping_patience):
            print(f'  Early stop: no improvement in '
                  f'{config.early_stopping_patience} generations')
            stopped_early = True
            break

        # Build next gen
        elites = get_elites(population, config.elitism_count)
        children = []
        n_children_needed = config.population_size - config.elitism_count
        for _ in range(n_children_needed):
            parent_a = tournament_select(
                population, config.tournament_size, rng
            )
            parent_b = tournament_select(
                population, config.tournament_size, rng
            )
            child_genome = reproduce_fn(
                parent_a, parent_b, pp, rng,
                config.crossover_rate, config.mutation_rate,
            )
            child_fitness = fitness_fn(child_genome)
            children.append((child_genome, child_fitness))

        if local_search_fn is not None:
            polished = []
            for g, f in elites:
                g_new, f_new = local_search_fn(g, f)
                polished.append((g_new, f_new))
            elites = polished

        population = elites + children

    total_seconds = time.perf_counter() - start_time
    print(f'Evolution complete in {total_seconds:.1f}s. '
          f'Best fitness: {best_fitness:.1f}')

    return EvolveResult(
        best_genome=best_genome,
        best_fitness=best_fitness,
        history=history,
        total_seconds=total_seconds,
        stopped_early=stopped_early,
    )