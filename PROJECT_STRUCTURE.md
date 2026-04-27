# UniversityTimeTable — Project Structure & Schema Reference

## File-by-File Structure

```
UniversityTimeTable/
├── main.py                         — CLI entry point (phase1 / phase2 / all)
├── requirements.txt                — numpy, pandas, PyYAML
├── scripts/
│   ├── config.yaml                 — All runtime parameters
│   └── view_schedule.py            — Generates an HTML visual schedule
├── data/
│   ├── data.xml                    — The Purdue dataset (primary input)
│   └── data_shape.md               — Human-readable data summary
├── outputs/
│   └── schedule.html               — Generated visual output
├── results/
│   ├── run_*_best.npy              — Phase 1 best genome (class→room/time assignment)
│   ├── run_*.json                  — Phase 1 run log (GA history, fitness breakdown)
│   ├── phase2_*_order.npy          — Phase 2 best genome (student processing order)
│   ├── phase2_*_assignment.json    — Final student→section mapping
│   └── phase2_*_log.json           — Phase 2 run log
└── src/
    ├── core/                       — Shared infrastructure
    │   ├── models.py               — All dataclasses (Room, Class, Student, Timetable, …)
    │   ├── parser.py               — XML → model objects
    │   ├── preprocessor.py         — Derived data for GA speed (masks, conflict graph)
    │   ├── ga.py                   — Generic GA evolve() loop
    │   └── utils.py                — Config loading, JSON saving
    ├── scheduling/                 — Phase 1: course scheduling
    │   ├── chromosome.py           — Genome: (n_classes, 2) int array [room_idx, time_idx]
    │   ├── fitness.py              — Aggregates hard+soft → scalar score
    │   ├── operators.py            — init_population, uniform_crossover, reproduce
    │   ├── local_search.py         — Optional hill-climb memetic step
    │   ├── main.py                 — Phase 1 driver
    │   └── constraints/
    │       ├── hard.py             — Room conflicts, instructor conflicts, room sharing
    │       ├── soft.py             — Preferences, instructor workload, capacity
    │       └── group.py            — All 14 group constraint types
    └── sectioning/                 — Phase 2: student sectioning
        ├── chromosome.py           — Genome: 1D permutation of student IDs
        ├── fitness.py              — Penalty for skipped/conflicted enrollments
        ├── sectioner.py            — Greedy student→section assignment algorithm
        ├── operators.py            — Order crossover (OX), swap mutation
        └── main.py                 — Phase 2 driver
```

---

## How the Files Connect

```
data.xml
   │
   ▼
parser.py  ──────────────────────►  Timetable (models.py)
                                          │
                                          ▼
                                   preprocessor.py
                                   PreprocessedData
                            ┌─── time_masks (2016-bit arrays per class/time)
                            ├─── conflict_graph (which classes can't overlap)
                            ├─── instructor_to_classes
                            ├─── gc_to_classes / class_to_gcs
                            ├─── dsatur_order (initialization hint)
                            └─── meet_with_exempt_pairs

                                          │
              ┌───────────────────────────┴─────────────────────────────┐
              │ PHASE 1                                                  │ PHASE 2
              ▼                                                          ▼
  scheduling/chromosome.py                                 sectioning/chromosome.py
  genome: (n_classes, 2) int array                         genome: student ID permutation
  [room_idx, time_idx] per class                           defines processing order
              │                                                          │
  scheduling/fitness.py                                   sectioner.py
  ├── hard.py: room/instructor                             Greedy: for each student
  │   conflicts, sharing                                   in order → pick best section
  ├── soft.py: preferences,                                that fits capacity & no time
  │   workload, capacity                                   conflict with existing schedule
  └── group.py: 14 constraint types                                      │
              │                                            sectioning/fitness.py
              └──────────────┐   ┌────────────────────────┘
                             ▼   ▼
                           ga.py evolve()  ◄── config.yaml
                      tournament selection
                      elitism + crossover + mutation
                      optional local_search (hill-climb)
                             │
                       results/*.npy/.json
                             │
                    view_schedule.py → outputs/schedule.html
```

---

## Two-Phase Design

### Phase 1 — Course Scheduling (`src/scheduling/`)

Each class is encoded as a pair `[room_index, time_index]` — indices into that class's own candidate lists from the XML. The GA evolves minimizing a weighted fitness score:

**Hard violations** (weight ×1000 each):
- Room double-booking (two classes in the same room at the same time)
- Instructor double-booking (same instructor assigned to overlapping classes)
- Room sharing violations (class scheduled during a time blocked for another department)
- Group constraint `P`-pref violations (Prohibited constraints broken)

**Soft penalties** (raw score added):
- Room/time preference scores (from the XML `pref` attributes)
- Capacity overflows (class limit > room capacity, ×500 per violation)
- Instructor workload (daily minutes > 6h or consecutive > 3h)
- Group constraint `R`-pref and float-pref violations

**Local search** (optional, disabled by default): A hill-climb memetic step applied to the top-k elites every N generations. Exhaustively tries all `(room, time)` combinations per class — expensive but precise.

### Phase 2 — Student Sectioning (`src/sectioning/`)

Takes the Phase 1 assignment as fixed and evolves the **order in which students get processed** by a greedy sectioner. Since sections fill up as students are placed, the processing order determines who gets their preferred section.

**Greedy sectioner** (`sectioner.py`):
1. Process students in chromosome order.
2. For each student, iterate their requested offerings.
3. For each offering, iterate its subparts (lecture, lab, etc.).
4. Pick the valid section with the most remaining capacity (load-balancing).
5. Valid = no time conflict with the student's already-assigned classes + capacity > 0.
6. If no section fits, record as skipped.

**Phase 2 fitness**:
```
fitness = 1000 × n_enrollments_skipped
        +    5 × n_time_conflicts_avoided
        +    5 × n_capacity_rejections
```

**Crossover**: Order Crossover (OX) — preserves relative ordering of student IDs from each parent, which is required since the genome is a permutation.

---

## Key Data Types (models.py)

| Class | Description |
|---|---|
| `Room` | Frozen dataclass: id, capacity, constraint, location, sharing |
| `RoomSharing` | Frozen dataclass: pattern string, unit_minutes, departments dict |
| `TimePattern` | Frozen dataclass: days bitmask, start slot, length, break_time, pref |
| `RoomCandidate` | Frozen dataclass: room_id, pref score |
| `Class` | Mutable dataclass: all class attributes + lists of candidates |
| `Enrollment` | Frozen dataclass: offering_id, weight |
| `Student` | Mutable dataclass: id, list of Enrollments |
| `GroupConstraint` | Mutable dataclass: id, type string, pref, list of class_ids |
| `Timetable` | Top-level container with fast-lookup dicts (rooms_by_id, etc.) |

---

## Configuration (`scripts/config.yaml`)

| Key | Description |
|---|---|
| `data.input_path` | Path to the XML dataset |
| `data.subset` | Max classes to load (null = all 896) |
| `student_sectioning.sample_size` | Max students for Phase 2 (null = all 30,846) |
| `ga.*` | Phase 1 GA parameters (pop size, generations, rates, seed) |
| `phase2.ga.*` | Phase 2 GA parameters (separate, smaller by default) |
| `local_search.enabled` | Toggle hill-climb memetic step |
| `local_search.top_k` | How many elites to polish per generation |
| `local_search.apply_every_n_gens` | Throttle to save runtime |
| `fitness.hard_weight` | Multiplier for hard violations (default 1000) |
| `output.results_dir` | Where to save `.npy` and `.json` results |
| `output.outputs_dir` | Where to save visual HTML output |
