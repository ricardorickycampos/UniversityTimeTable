
from __future__ import annotations

import numpy as np
from src.core.preprocessor import PreprocessedData

"""Phase 2 chromosome: a permutation of student IDs.

In Phase 2 a chromosome is a 1D array of student IDs, defining
the order in which students get processed by the greedy sectioner.
Different orders produce different outcomes because capacity fills up
as students get placed.
"""

def random_chromosome(pp: PreprocessedData, rng: np.random.Generator) -> np.ndarray:
    student_ids = np.array([s.id for s in pp.timetable.students], dtype=np.int32)
    rng.shuffle(student_ids)  # in-place shuffle
    return student_ids

def mutate_one_gene(
    genome: np.ndarray,
    class_idx: int,
    pp: PreprocessedData,
    rng: np.random.Generator,
) -> np.ndarray:
    new_genome = genome.copy()
    n = len(new_genome)
    swap_with = int(rng.integers(n))
    while swap_with == class_idx and n > 1:
        swap_with = int(rng.integers(n))
    new_genome[class_idx], new_genome[swap_with] = new_genome[swap_with], new_genome[class_idx]
    return new_genome

def mutate_many_genes(
    genome: np.ndarray,
    pp: PreprocessedData,
    rng: np.random.Generator,
    p_mutation: float,
) -> np.ndarray:
    """Apply per-position swap mutation.
    For each position, with probability p_mutation, swap it with a
    random other position. Expected number of swaps per call:
    n_students * p_mutation.
    """
    new_genome = genome.copy()
    n = len(new_genome)
    positions_to_mutate = np.where(rng.random(n) < p_mutation)[0]
    for pos in positions_to_mutate:
        swap_with = int(rng.integers(n))
        if swap_with != pos:
            new_genome[pos], new_genome[swap_with] = new_genome[swap_with], new_genome[pos]

    return new_genome
