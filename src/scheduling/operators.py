from __future__ import annotations

from typing import Callable
import numpy as np
from src.core.preprocessor import PreprocessedData
from src.scheduling.chromosome import random_chromosome, mutate_many_genes

"""Genetic algorithm operators: init, select, crossover, mutate.

An "operator" here is a function that takes some input and produces a modified or new output. The engine.py
loop calls these in a fixed sequence every generation.
"""
def init_population(
    pp: PreprocessedData,
    size: int,
    fitness_fn: Callable[[np.ndarray], float],
    rng: np.random.Generator,
) -> list:
    """Create `size` random individuals, each with its fitness evaluated."""
    population = []
    for _ in range(size):
        genome = random_chromosome(pp, rng)
        fitness = fitness_fn(genome)
        population.append((genome, fitness))
    return population

def uniform_crossover(
    parent_a: np.ndarray,
    parent_b: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    """Create a child genome by independently picking each gene from A or B."""
    assert parent_a.shape == parent_b.shape
    n = parent_a.shape[0]

    # For each row, True means take from A, False means take from B
    from_a_mask = rng.random(n) < 0.5

    child = np.where(from_a_mask[:, np.newaxis], parent_a, parent_b)
    return child.astype(np.int32)

def reproduce(
    parent_a: np.ndarray,
    parent_b: np.ndarray,
    pp: PreprocessedData,
    rng: np.random.Generator,
    crossover_rate: float,
    mutation_rate: float,
) -> np.ndarray:
    """Produce one child from two parents. """
    if rng.random() < crossover_rate:
        child = uniform_crossover(parent_a, parent_b, rng)
    else:
        child = parent_a.copy()

    child = mutate_many_genes(child, pp, rng, mutation_rate)
    return child
