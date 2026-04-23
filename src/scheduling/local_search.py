from __future__ import annotations

from typing import Callable
import numpy as np
from src.core.preprocessor import PreprocessedData

"""Hill-climbing local search."""

def hill_climb(
    genome: np.ndarray,
    fitness: float,
    pp: PreprocessedData,
    fitness_fn: Callable[[np.ndarray], float],
    rng: np.random.Generator,
    max_passes: int = 5,
    verbose: bool = False,
) -> tuple:
    """
    The algorithm:
      1. Walk classes in random order.
      2. For each class, try every valid (room_idx, time_idx) pair.
      3. If any choice beats the current best, commit it.
      4. After a full pass, if ANY class was improved, start another pass.
      5. Stop when a full pass improves nothing, or at max_passes.

    A single pass is O(n_classes × avg_domain_size × fitness_cost).
    domain_size referring to the number of candidate times/rooms for a given room.
    SUPER EXPENSIVE
    Returns:
        (improved_genome, improved_fitness) tuple. Always returns a NEW
        array; never mutates input.
    """
    current = genome.copy()
    current_fit = fitness
    n = len(pp.timetable.classes)

    for pass_num in range(max_passes):
        improved_this_pass = False

        # Shuffle class order to avoid processing bias
        class_order = np.arange(n)
        rng.shuffle(class_order)

        for class_idx in class_order:
            cls = pp.timetable.classes[class_idx]
            if not cls.candidate_rooms and not cls.candidate_times:
                continue  # nothing to vary on this class

            # Original values to restore between trials
            orig_room = int(current[class_idx, 0])
            orig_time = int(current[class_idx, 1])
            best_room, best_time = orig_room, orig_time
            best_fit = current_fit

            n_rooms = len(cls.candidate_rooms) if cls.candidate_rooms else 1
            n_times = len(cls.candidate_times) if cls.candidate_times else 1

            # Try every combination for this class
            for r in range(n_rooms):
                for t in range(n_times):
                    if r == orig_room and t == orig_time:
                        continue  # already tested as the baseline
                    if cls.candidate_rooms:
                        current[class_idx, 0] = r
                    if cls.candidate_times:
                        current[class_idx, 1] = t
                    trial_fit = fitness_fn(current)
                    if trial_fit < best_fit:
                        best_fit = trial_fit
                        best_room, best_time = r, t

            # Commit best found
            if cls.candidate_rooms:
                current[class_idx, 0] = best_room
            if cls.candidate_times:
                current[class_idx, 1] = best_time

            if best_fit < current_fit:
                current_fit = best_fit
                improved_this_pass = True
        if verbose:
            print(f'    hill_climb pass {pass_num}: '
                  f'fitness={current_fit:.1f} '
                  f'{"(improved)" if improved_this_pass else "(no change)"}')

        if not improved_this_pass:
            break  # local optimum reached
    return current, current_fit


def make_local_search_fn(
    pp: PreprocessedData,
    fitness_fn: Callable[[np.ndarray], float],
    rng: np.random.Generator,
    max_passes: int = 5,
) -> Callable:
    """ Builds it closer to what GA engine expects for returning."""
    def _local_search(genome: np.ndarray, fit: float) -> tuple:
        return hill_climb(
            genome=genome,
            fitness=fit,
            pp=pp,
            fitness_fn=fitness_fn,
            rng=rng,
            max_passes=max_passes,
            verbose=False,
        )
    return _local_search