# UniTime Data Scheme 

The XML is in **UniTime format** (a standard academic timetabling format).


The root `<timetable>` element has four children:

```
<timetable>
├── <rooms>            — 63 physical classrooms
├── <classes>          — 896 course sections
├── <students>         — 30,846 students with their course wish lists
└── <groupConstraints> — ordering/co-scheduling rules between classes
```

### `<room>` schema

| Attribute | Type | Description |
|---|---|---|
| `id` | int | Unique room ID |
| `capacity` | int | Seats available |
| `constraint` | bool | Whether this room participates in conflict checking (true for all 63) |
| `location` | "x,y" | Campus map coordinate (parsed but currently unused) |
| `<sharing>` | optional | Department time-sharing block for shared rooms |

The `<sharing>` sub-element encodes which departments can use a room in each time window using a pattern string like `"FFF000XXX111..."` where each character covers `unit × 5` minutes:
- `F` = free for all departments
- `X` = unavailable
- digit = department code mapped via `<department>` sub-tags

### `<class>` schema

| Attribute | Type | Description |
|---|---|---|
| `id` | int | Unique class (section) ID |
| `offering` | int | Course offering this section belongs to |
| `config` | int | Configuration variant (some courses have lecture+lab configs) |
| `subpart` | int | Role within config (lecture vs. lab within a config) |
| `classLimit` | int | Max enrollment allowed |
| `department` | int | Owning department |
| `scheduler` | int (opt) | Assigned scheduler |
| `committed` | bool | Whether the assignment is already fixed |
| `dates` | bitmask string | Which weeks of the semester this class meets |
| `parent` | int (opt) | Parent class ID (child classes inherit `offering`/`config`) |
| `<instructor id>` | list | Assigned instructor IDs |
| `<room id pref>` | list | Candidate rooms with preference scores (`R`=required, `P`=prohibited, or float) |
| `<time days start length breakTime pref>` | list | Candidate time slots |

Time slots: `days` is a 7-char bitmask `"1010100"` (M/W/F). `start` is a 5-minute slot index from midnight. The week grid is 7 days × 288 slots = **2016 cells** of 5-minute granularity.

### `<student>` schema

| Attribute | Type | Description |
|---|---|---|
| `id` | int | Student ID |
| `<offering id weight>` | list | Courses the student wants to enroll in (with priority weight) |

Students don't request specific sections — that's what Phase 2 decides.

### `<constraint>` (groupConstraints) schema

| Attribute | Type | Description |
|---|---|---|
| `id` | int | Constraint ID |
| `type` | string | One of 14 types (see below) |
| `pref` | float/R/P | `R`=required (soft, heavy), `P`=prohibited (hard), float = soft weight |
| `<class id>` | list | The class IDs this constraint applies to |

Constraint types: `SAME_ROOM`, `SAME_TIME`, `MEET_WITH`, `SAME_START`, `SAME_DAYS`, `SAME_INSTR`, `DIFF_TIME`, `SAME_STUDENTS`, `BTB`, `BTB_TIME`, `NHB(1.5)`, `NHB_GTE(1)`, `CAN_SHARE_ROOM`, `SPREAD`.

---