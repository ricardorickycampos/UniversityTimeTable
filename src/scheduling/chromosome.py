"""Chromosome construction and single-gene mutation.

A chromosome is an int numpy array of shape (n_classes, 2).
Column 0 = chosen room index (into candidate_rooms).
Column 1 = chosen time index (into candidate_times).
"""
from __future__ import annotations

import numpy as np
from src.core.preprocessor import PreprocessedData

def random_chromosome(pp: PreprocessedData, rng: np.random.Generator) -> np.ndarray:
    """Create a validly encoded random chromosome.
    Args:
        @pp: Preprocessed data
        @rng: numpy Generator
    Returns:
        (n_classes, 2) int array.
    """
    n = len(pp.timetable.classes)
    genome = np.zeros((n, 2), dtype=np.int32)

    for class_idx, cls in enumerate(pp.timetable.classes):
        # Decide room index
        if len(cls.candidate_rooms) == 0:
            # No candidate rooms, Leave at 0.
            genome[class_idx, 0] = 0
        elif len(cls.candidate_rooms) == 1:
            # Only 1 option. Pin to 0.
            genome[class_idx, 0] = 0
        else:
            # For Multiple options. Random choice from 0 to len(candidate_rooms)
            genome[class_idx, 0] = rng.integers(len(cls.candidate_rooms))

        # Decide time index
        if len(cls.candidate_times) == 0:
            genome[class_idx, 1] = 0
        elif len(cls.candidate_times) == 1:
            genome[class_idx, 1] = 0
        else:
            genome[class_idx, 1] = rng.integers(len(cls.candidate_times))
    return genome

def mutate_one_gene(
    genome: np.ndarray,
    class_idx: int,
    pp: PreprocessedData,
    rng: np.random.Generator,
) -> np.ndarray:
    """Replace one class's gene pair with a random valid alternative.
    Returns a new genome.
    """
    new_genome = genome.copy()
    cls = pp.timetable.classes[class_idx]
    if cls.candidate_rooms:
        new_genome[class_idx, 0] = rng.integers(len(cls.candidate_rooms))
    if cls.candidate_times:
        new_genome[class_idx, 1] = rng.integers(len(cls.candidate_times))
    return new_genome


def mutate_many_genes(
    genome: np.ndarray,
    pp: PreprocessedData,
    rng: np.random.Generator,
    p_mutation: float,
) -> np.ndarray:
    """Apply mutation with probability p_mutation per class."""
    new_genome = genome.copy()
    n = len(pp.timetable.classes)
    # Index which one to mutate, then iterates on 'True' ones
    to_mutate = np.where(rng.random(n) < p_mutation)[0]

    for class_idx in to_mutate:
        cls = pp.timetable.classes[class_idx]
        if cls.candidate_rooms:
            new_genome[class_idx, 0] = rng.integers(len(cls.candidate_rooms))
        if cls.candidate_times:
            new_genome[class_idx, 1] = rng.integers(len(cls.candidate_times))

    return new_genome