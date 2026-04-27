# `/src` Folder — Detailed File Explanations

## Entry Point — `main.py`

This is the only file you ever call directly. It's a CLI router with three commands:

```bash
python main.py phase1 --config scripts/config.yaml
python main.py phase2 --config scripts/config.yaml --genome results/run_xyz_best.npy
python main.py all    --config scripts/config.yaml
```

- `phase1` → calls `src/scheduling/main.py::run_phase1(config_path)`
- `phase2` → calls `src/sectioning/main.py::run_phase2(config_path, genome_path)`
- `all` → calls both sequentially: runs phase1, reads the output genome path from the saved JSON log, then feeds it into phase2

That's all `main.py` does — it parses args and dispatches. All real logic lives in `src/`.

---

## `src/core/` — Shared Infrastructure

These five files are used by **both** phases. They have no knowledge of the GA problem itself — they're pure data and utilities.

---

### `src/core/models.py`

**What it does:** Defines every data class in the project using Python `@dataclass`. Nothing is computed here — it's pure structure.

| Class | Frozen? | Fields |
|---|---|---|
| `Room` | yes | id, capacity, constraint, location, sharing |
| `RoomSharing` | yes | pattern string, unit_minutes, departments dict |
| `RoomCandidate` | yes | room_id, pref score |
| `TimePattern` | yes | days bitmask, start, length, break_time, pref |
| `Class` | no | id, offering, config, subpart, class_limit, department, instructor_ids, candidate_rooms, candidate_times, parent_id |
| `Enrollment` | yes | offering_id, weight |
| `Student` | no | id, list of Enrollments |
| `GroupConstraint` | no | id, type string, pref, list of class_ids |
| `Timetable` | no | everything above as lists + fast-lookup dicts (rooms_by_id, classes_by_id, etc.) |

It also defines three helpers used throughout constraint checking:
- `parse_pref(raw)` — converts `"R"` → `-1000.0`, `"P"` → `1000.0`, or parses a float
- `is_required(pref)` — true if pref ≤ -1000
- `is_prohibited(pref)` — true if pref ≥ 1000

**How `main.py` reaches it:** Indirectly — `parser.py` builds these objects and returns a `Timetable`, which everything else holds onto.

---

### `src/core/parser.py`

**What it does:** Reads `data/data.xml` and returns a fully populated `Timetable` object. The only file that ever touches the XML.

The parsing flow:
1. `parse_data(path, subset)` opens the XML with `xml.etree.ElementTree`
2. Calls four per-entity parsers: `_parse_room`, `_parse_class`, `_parse_student`, `_parse_group_constraint`
3. Calls `_resolve_parent_inheritance` — some classes have `offering=-1` in the XML, meaning they inherit it from their parent class. This loops up to 10 passes to resolve chains
4. If `subset=N` is set, trims to the first N classes and removes students/constraints that reference removed classes
5. Returns a `Timetable`

Key detail on `_parse_days`: the XML days field `"1010100"` is a 7-character string. The parser converts it to an integer bitmask where bit 0 = Monday, bit 6 = Sunday. This bitmask format is what all constraint checks use.

**How `main.py` reaches it:** Both phase drivers call `parse_data(data_path, subset=subset)` as their first step.

---

### `src/core/preprocessor.py`

**What it does:** Takes the `Timetable` and builds all the derived data structures that the GA needs to run fast. Computed once and cached in a `PreprocessedData` object passed everywhere.

The five structures it builds:

**`time_masks`** — For each class, for each of its candidate times, a flat boolean numpy array of length 2016 (7 days × 288 slots). A `True` at position `i` means "this class occupies 5-minute slot `i` during the week." This makes overlap checking a single `np.any(mask_a & mask_b)` operation instead of a nested loop.

**`instructor_to_classes`** — Dict mapping each instructor ID to the list of class indices they teach. Used to quickly find all pairs of classes that share an instructor.

**`gc_to_classes` / `class_to_gcs`** — Lookup tables in both directions between group constraints and the class indices they involve.

**`conflict_graph`** — A list of sets. `conflict_graph[i]` is the set of class indices that class `i` must not overlap in time with (due to shared instructor or SAME_STUDENTS/DIFF_TIME constraints).

**`dsatur_order`** — Class indices sorted from most-conflicting to least (by degree in the conflict graph). Used to seed the initial GA population — harder classes (more constrained) get assigned first, which tends to produce better starting chromosomes.

**`meet_with_exempt_pairs`** — Set of `(min_idx, max_idx)` pairs that are explicitly allowed to share a room and time (MEET_WITH or CAN_SHARE_ROOM constraints). These are skipped during conflict checking.

**How `main.py` reaches it:** Both phase drivers call `preprocess(tt)` immediately after parsing, then pass `pp` into every downstream function.

---

### `src/core/ga.py`

**What it does:** The generic GA evolution loop. It knows nothing about timetabling — it works entirely through injected functions.

Key types:
- `GAConfig` — all hyperparameters: population size, generations, crossover/mutation rates, tournament size, elitism count, seed
- `GenerationStats` — best/avg/worst fitness + elapsed time for one generation
- `EvolveResult` — best genome found, fitness, full history list, total time, early-stop flag

The `evolve()` function signature:
```python
evolve(pp, fitness_fn, config, local_search_fn, init_pop_fn, reproduce_fn)
```

Each generation it:
1. Records stats for the current population
2. Checks early stopping (if fitness hasn't improved in N generations)
3. Preserves the top `elitism_count` individuals unchanged
4. Runs tournament selection + `reproduce_fn` to fill the rest of the next generation
5. Optionally applies `local_search_fn` to the elites

Population is stored as a list of `(genome, fitness)` tuples. "Best" always means lowest fitness (minimization problem).

**How `main.py` reaches it:** Both phase drivers import and call `evolve()`, injecting their own `fitness_fn`, `init_pop_fn`, and `reproduce_fn`.

---

### `src/core/utils.py`

**What it does:** Three small helpers.
- `load_config(path)` — reads `config.yaml` with PyYAML and returns a dict
- `json_default(o)` — JSON encoder that handles numpy types (otherwise `json.dump` crashes on `np.int32`, `np.float64`, etc.)
- `save_run_log(path, run_log)` — writes a dict to a JSON file using the above encoder

**How `main.py` reaches it:** Both phase drivers use all three when reading config and saving results.

---

## `src/scheduling/` — Phase 1: Course Scheduling

These files solve: *assign each class to one room and one time slot.*

---

### `src/scheduling/main.py`

**What it does:** The Phase 1 driver — orchestrates the full run end to end.

Execution order:
1. Reads `config.yaml` via `utils.load_config`
2. Calls `parser.parse_data` → `Timetable`
3. Calls `preprocessor.preprocess` → `PreprocessedData`
4. Builds `fitness_fn` as a lambda closing over `pp` and `hard_weight`
5. Optionally wraps a `local_search_fn` (throttled so it only fires every N calls)
6. Calls `ga.evolve()` with Phase 1's `init_population` and `reproduce` operators
7. Calls `evaluate_detailed` on the best genome for the final report
8. Saves the best genome as `results/run_{timestamp}_{size}_{score}_best.npy`
9. Saves the full run log as `results/run_{timestamp}_{size}_{score}.json`
10. Returns the log path (used by `main.py all` to chain into Phase 2)

---

### `src/scheduling/chromosome.py`

**What it does:** Defines what a Phase 1 genome is and how to create/mutate one.

A Phase 1 genome is a numpy array of shape `(n_classes, 2)` where:
- Column 0 = chosen room index (into `cls.candidate_rooms`)
- Column 1 = chosen time index (into `cls.candidate_times`)

These are indices into each class's own candidate lists — not global room/time IDs. So gene `[2, 5]` for class 10 means "use class 10's 3rd candidate room and 6th candidate time."

Functions:
- `random_chromosome(pp, rng)` — creates a genome by picking random valid indices for each class
- `mutate_one_gene(genome, class_idx, pp, rng)` — replaces one class's gene pair with a new random choice
- `mutate_many_genes(genome, pp, rng, p_mutation)` — applies per-class mutation with probability `p_mutation`

---

### `src/scheduling/operators.py`

**What it does:** Implements the GA operators injected into `ga.evolve()`.

- `init_population(pp, size, fitness_fn, rng)` — creates `size` random chromosomes, evaluates each, returns list of `(genome, fitness)` tuples

- `uniform_crossover(parent_a, parent_b, rng)` — for each class (row), independently picks that row from parent A or parent B with 50/50 probability. Works well because each class's gene is independent of other classes.

- `reproduce(parent_a, parent_b, pp, rng, crossover_rate, mutation_rate)` — with probability `crossover_rate` applies uniform crossover, otherwise clones parent A, then applies `mutate_many_genes`

---

### `src/scheduling/fitness.py`

**What it does:** Aggregates all constraint scores into one scalar fitness number.

- `evaluate(pp, assignment, hard_weight)` → float — the scalar used inside the GA loop
- `evaluate_detailed(pp, assignment, hard_weight)` → dict — the full breakdown used for logging and the schedule viewer

The formula:
```
fitness = hard_weight × hard_total + soft_total
```

Where `hard_weight = 1000` by default, so a single hard violation costs 1000 points — effectively making hard constraints non-negotiable.

It calls all three constraint modules and combines their results into one dict with keys: `fitness`, `hard_total`, `soft_total`, `hard` (breakdown), `soft` (breakdown), `is_feasible`.

---

### `src/scheduling/constraints/hard.py`

**What it does:** Counts hard constraint violations. Returns raw integer counts (not weighted).

Three checks:

**`check_room_conflicts`** — Groups classes by their assigned room. For every pair of classes in the same room, does `np.any(mask_a & mask_b)`. If their time masks overlap and the pair isn't in `meet_with_exempt_pairs`, it's a violation.

**`check_instructor_conflicts`** — Same logic but grouped by instructor ID using `pp.instructor_to_classes`.

**`check_room_sharing`** — For each class in a room that has a sharing pattern, checks every occupied 5-minute slot against the pattern character. If the slot is `X` (unavailable) or belongs to a different department, it's a violation.

`count_hard_violations` runs all three and returns a dict with individual counts plus a total.

---

### `src/scheduling/constraints/soft.py`

**What it does:** Scores soft constraint penalties. Returns floats (not counts).

Three scorers:

**`score_preferences`** — Sums the `pref` value for every class's chosen room and time. Negative prefs (preferred choices) reduce the score; positive prefs increase it.

**`score_capacity`** — Calls `check_capacity` from `hard.py` (reused) and multiplies by 500. If a class limit exceeds room capacity it adds 500 to the score per violation.

**`score_instructor_workload`** — For each instructor, unions all their time masks into a single weekly occupancy array. Then per day:
- If total teaching minutes > 360 (6h), penalises the excess at 0.05 per minute
- If longest consecutive block > 180 (3h), penalises the excess at 0.10 per minute

---

### `src/scheduling/constraints/group.py`

**What it does:** Handles all 14 group constraint types from the XML. Each constraint links a set of classes and says they must/should satisfy some relationship.

The dispatch table maps each type string to a checker function:

| Type | What it checks |
|---|---|
| `SAME_ROOM` | All classes must be in the same room |
| `SAME_TIME` / `MEET_WITH` | All classes must have identical day/start/length |
| `SAME_START` | All classes must start at the same slot |
| `SAME_DAYS` | All classes must meet on the same days |
| `SAME_INSTR` | All classes must share at least one common instructor |
| `DIFF_TIME` / `SAME_STUDENTS` | No two classes may overlap in time |
| `BTB` / `BTB_TIME` | Consecutive classes must be back-to-back |
| `NHB(1.5)` | Classes must be exactly 1.5 hours apart |
| `NHB_GTE(1)` | Classes must be at least 1 hour apart |
| `CAN_SHARE_ROOM` | No-op (exempt, always passes) |
| `SPREAD` | Classes should be spread across different days |

`check_all_group_constraints` iterates every constraint, calls its handler, then routes the result:
- `pref = P` (Prohibited) → hard violation count +1
- `pref = R` (Required) → soft penalty += 200 × magnitude
- `pref = float` → soft penalty += abs(pref) × magnitude

---

### `src/scheduling/local_search.py`

**What it does:** An optional hill-climbing memetic step applied to elite individuals.

`hill_climb` algorithm:
1. Shuffle class order (avoids processing bias)
2. For each class, try **every** valid `(room_idx, time_idx)` combination
3. Commit whichever combination gives the lowest fitness
4. If any class improved this pass, do another pass
5. Stop when a full pass improves nothing, or `max_passes` is reached

This is very expensive — O(n_classes × avg_domain_size × fitness_cost) per pass — which is why it's disabled by default and throttled when enabled.

`make_local_search_fn` wraps `hill_climb` into the signature `(genome, fitness) → (genome, fitness)` that `ga.evolve()` expects.

---

## `src/sectioning/` — Phase 2: Student Sectioning

These files solve the second problem: *given a fixed room/time schedule, assign each student to a specific section of each course they want.*

---

### `src/sectioning/main.py`

**What it does:** The Phase 2 driver — mirrors Phase 1's structure.

Execution order:
1. Loads config and the Phase 1 genome (`.npy` file)
2. Parses and preprocesses the same XML data
3. Optionally samples a subset of students (controlled by `student_sectioning.sample_size` in config)
4. Calls `build_offering_index` to map offering_id → subpart_id → [class_ids]
5. Builds `fitness_fn` as a closure over `pp`, `phase1_assignment`, and `offering_index`
6. Calls `ga.evolve()` — the same shared engine — with Phase 2's operators
7. Calls `evaluate_detailed` for the final report
8. Saves three output files:
   - `_order.npy` — best student processing order
   - `_assignment.json` — full student→section mapping
   - `_log.json` — GA history

---

### `src/sectioning/chromosome.py`

**What it does:** Defines what a Phase 2 genome is — completely different from Phase 1.

A Phase 2 genome is a **1D array of student IDs** — a permutation. Its length equals the number of students. The order determines who the greedy sectioner processes first (earlier = better chance at preferred sections).

- `random_chromosome(pp, rng)` — shuffles all student IDs randomly
- `mutate_one_gene` — swaps two positions in the permutation
- `mutate_many_genes` — applies per-position swap with probability `p_mutation`

Since it's a permutation, the same crossover as Phase 1 cannot be used (that would create duplicate student IDs).

---

### `src/sectioning/operators.py`

**What it does:** Phase 2's GA operators — permutation-safe versions.

**`order_crossover` (OX):**
1. Copy a random contiguous segment `[i, j)` from parent A into the child
2. Fill the remaining positions (starting from `j`, wrapping) with values from parent B in the order they appear, skipping any already in the child

This preserves the relative ordering of student IDs from each parent without creating duplicates — the correct crossover for permutation chromosomes.

`reproduce` applies OX with probability `crossover_rate`, otherwise clones parent A, then applies `mutate_many_genes`.

---

### `src/sectioning/sectioner.py`

**What it does:** The greedy section assignment algorithm — the core of Phase 2.

`build_offering_index(pp)` builds a nested dict: `offering_id → subpart_id → [class_ids]`. This is the lookup used to find which sections a student can go into for each course.

`section_students(pp, phase1_assignment, student_order, offering_index)` runs the greedy algorithm:

```
for each student_id in student_order:
    for each enrollment (course request) the student has:
        for each subpart of that course (lecture, lab, etc.):
            pick the section with the most remaining capacity
            that doesn't conflict with the student's existing schedule
        if all subparts found → commit, update capacity counts, update student's time mask
        if any subpart failed → skip this enrollment entirely
```

`_pick_best_section` does the actual selection — rejects sections that are full or would cause a time overlap with the student's accumulated time mask, then picks the one with the most remaining capacity (load balancing).

Returns a `SectioningResult` with the full assignment dict plus statistics (placed, skipped, conflict avoidances, capacity rejections).

---

### `src/sectioning/fitness.py`

**What it does:** Scores a student-order chromosome by running the greedy sectioner and penalising bad outcomes.

```
fitness = 1000 × n_enrollments_skipped
        +    5 × n_time_conflicts_avoided
        +    5 × n_capacity_rejections
```

Skipped enrollments dominate at ×1000 — a student who couldn't be placed in any section for a course is the worst outcome. Conflict/capacity rejections at ×5 are minor signal about how tight the schedule is.

- `evaluate` → scalar float (used inside GA loop)
- `evaluate_detailed` → full dict with coverage %, per-component penalties, and the raw `SectioningResult` object (used for logging)

---

## Full Execution Flow Through `main.py`

```
python main.py all --config scripts/config.yaml
         │
         ▼
  run_complete_pipeline(config_path)
         │
    ┌────┴─────────────────────────────────────────────────────┐
    │ PHASE 1                                                   │
    │  scheduling/main.py::run_phase1()                        │
    │    utils.load_config()          ← config.yaml            │
    │    parser.parse_data()          ← data/data.xml          │
    │    preprocessor.preprocess()                             │
    │    fitness.evaluate() [lambda]                           │
    │    ga.evolve(                                            │
    │      init_pop_fn = operators.init_population             │
    │      reproduce_fn = operators.reproduce                  │
    │        └─ chromosome.random_chromosome()                 │
    │        └─ operators.uniform_crossover()                  │
    │        └─ chromosome.mutate_many_genes()                 │
    │      fitness_fn → fitness.evaluate()                     │
    │        └─ constraints/hard.count_hard_violations()       │
    │        └─ constraints/soft.score_soft_penalties()        │
    │        └─ constraints/group.check_all_group_constraints()│
    │    )                                                     │
    │    np.save()  → results/run_*_best.npy                   │
    │    utils.save_run_log() → results/run_*.json             │
    └───────────────────────┬──────────────────────────────────┘
                            │ genome_path from log
    ┌───────────────────────┴──────────────────────────────────┐
    │ PHASE 2                                                   │
    │  sectioning/main.py::run_phase2(genome_path)             │
    │    parser.parse_data() + preprocessor.preprocess()       │
    │    sectioner.build_offering_index()                      │
    │    ga.evolve(                                            │
    │      init_pop_fn = sectioning/chromosome.random_chromosome│
    │      reproduce_fn = sectioning/operators.reproduce       │
    │        └─ operators.order_crossover()                    │
    │        └─ chromosome.mutate_many_genes()                 │
    │      fitness_fn → sectioning/fitness.evaluate()          │
    │        └─ sectioner.section_students()                   │
    │    )                                                     │
    │    np.save()   → results/phase2_*_order.npy              │
    │    json.dump() → results/phase2_*_assignment.json        │
    │    utils.save_run_log() → results/phase2_*_log.json      │
    └──────────────────────────────────────────────────────────┘
```

The key architectural insight: `ga.py::evolve()` is completely generic — it's the same function for both phases. The difference is entirely in what gets injected:
- **Phase 1** injects a `(n_classes, 2)` chromosome with uniform crossover
- **Phase 2** injects a student-ID permutation with order crossover (OX)

Same engine, different representation.