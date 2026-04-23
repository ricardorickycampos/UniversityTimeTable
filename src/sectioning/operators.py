from __future__ import annotations


import numpy as np
from src.core.preprocessor import PreprocessedData
from src.sectioning.chromosome import mutate_many_genes


def order_crossover(
    parent_a: np.ndarray,
    parent_b: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    """Produce a child permutation from two parent permutations.
    Algorithm:
      1. Select a random contiguous segment [i, j) of the genome.
      2. Copy parent_a[i:j] directly into child[i:j].
      3. Scan parent_b starting from position j (wrapping around).
         For each value, if not already in the child, place it in the
         next empty child slot (also starting from j and wrapping).
    """
    assert parent_a.shape == parent_b.shape, "parents must be same length"
    n = len(parent_a)

    i = int(rng.integers(n))
    j = int(rng.integers(i + 1, n + 1))

    child = np.full(n, -1, dtype=parent_a.dtype)
    child[i:j] = parent_a[i:j]
    placed = set(int(x) for x in parent_a[i:j])

    write_pos = j % n
    for offset in range(n):
        read_pos = (j + offset) % n
        val = int(parent_b[read_pos])
        if val in placed:
            continue
        while child[write_pos] != -1:
            write_pos = (write_pos + 1) % n
        child[write_pos] = val
        placed.add(val)
        write_pos = (write_pos + 1) % n

    return child

def reproduce(
    parent_a: np.ndarray,
    parent_b: np.ndarray,
    pp: PreprocessedData,
    rng: np.random.Generator,
    crossover_rate: float,
    mutation_rate: float,
) -> np.ndarray:
    """Produce one child from two parents.
    """
    if rng.random() < crossover_rate:
        child = order_crossover(parent_a, parent_b, rng)
    else:
        child = parent_a.copy()

    child = mutate_many_genes(child, pp, rng, mutation_rate)
    return child
