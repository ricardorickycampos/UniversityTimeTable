![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

# <div align="center"> University Course Timetabling Problem (UCTP) </div>
---
This project aims to solve the University Course Timetabling Problem (UCTP) by designing a system capable of scheduling over 10,000 students and 500 courses at Kennesaw State University.

This is a collaborative effort for the Course CS 4306 - Algorithm Analysis
> Live demo website [_here_]([https://www.example.com](https://ricardorickycampos.github.io/UniversityTimeTable/))

## *Table of Contents*
* [General Info](#general-information)
* [Screenshots](#screenshots)
* [Implementation Details](#implementation-details)
* [Setup](#setup)
* [Project Structure](#project-structure)
* [Resources](#resources)
* [Authors](#authors)
* [License](#license)

## *General Information*

### Overview
**UniversityTimeTable** is a two-phase **Genetic Algorithm (GA)** solver for the University Course Timetabling Problem (UCTP), using a real dataset from Purdue University (Fall 2007), where the outcome of the two phases should be conflict-free and with minimized idle gaps.

- **Phase 1 - Course Scheduling:** schedule 896+ course sections to rooms and time slots 
- **Phase 2 - Student Sectioning:** assign 30,000+ students into those sections

### Goal 
- Generate a conflict-free schedule for a simulated university of 10,000+ students.
- Maximize compactness by minimizing idle gaps between lectures for students cohorts.
- Show runtime & improvement curves, explain ordering/pruning; provide one-command reproducibilty i.e. fixed seed.

### Constraints 
#### Hard
- **Non-Overlap:** (Conflict-Free): No double booking.
- **Room capacity:** Enrollment must not exceed a rooms seats. 
- **Resource & suitability:** Room much have required equipment for course.
- **Course structure relationships:** Valid combinations must be maintained e.i. lecture & labs. 
- **Instructor domain/qualification suitability:** Section must be assigned to a qualifed instructor.
- **Instructor availability & required preferences:** Explicitly blocked out times/days by instructors are non-negotiable.
- **Travel time limits:** For any individual, back to back classes must allow a feasible walk time.

#### Soft 
- **Minimizing student gaps:** Reduce idle time to as low as possible.
- **Hybrid modeling:** Allow courses marked as hybrid/online to use a virtual room.
- **Instructor workload distribution:** Define reasonable limits to instructors work time.
- **Preference satisfaction:** Track when a non-required faculty preference timeslop is honored.

## *Screenshots*


## *Implementation Details*
### Development Environment
- Python 3.10+

#### Install Require Dependency Libraries 
```bash
pip install -r requirements.txt
```

| Library | What will be used for |
|---|---|
| numpy | Core numerical engine — the genome arrays, the 2016-cell time bitmasks, all bitwise overlap checks (np.any(mask_a & mask_b)), random number generation (np.random.default_rng), and saving/loading genomes (.npy files) |
| pandas | Only used in explore.py — formats inspection results as DataFrames (schedule view, violations table, room usage, etc.) and in experiment.ipynb for plotting the GA history |
| PyYAML | Parses scripts/config.yaml at runtime via yaml.safe_load() in utils.py |

### Data Used
A real dataset from Purdue University (Fall 2007), which data and scheme are the following

&emsp;[Data](data/data.xml) <sub>*(.xml format)*</sub>
&emsp;[Data Schema](data/data-schema.md) <sub>*(.md format)*</sub>


### Setup
Before running the project, making changes in config.yaml file found in scripts/config.yaml
Algorithm takes them as parameters at runtime.

### How to run:
There are 2 different ways to run the project.
The first is doing the phases one at a time.<br>
Phase 1: Populates the Rooms and Courses data structures.<br>
Phase 2: Populates the Students data structure using the Rooms and Courses data structures from Phase 1.

 ```bash
    python3 main.py phase1 --config scripts/config.yaml
    python3 main.py phase2 --config scripts/config.yaml --genome results/(genome_file_name).npy
 ```
 NOTE: the --genome argument is optional, and will default to the last best genome found in the results/ folder.

 Second is all in one go.

 ```bash
    python3 main.py all --config scripts/config.yaml
```

### Results
After running, the output will be saved to the results/ folder.


## *Resources*

1. Abdipoor, S., Yaakob, R., Goh, S.L. and Abdullah, S., 2023. Meta-heuristic approaches for the university course
timetabling problem. Intelligent Systems with Applications, 19, p.200253.

## *Authors*
| Name | Role | GitHub |
|:----:|:----:|:------:|
| Cesar Arevalo Colocho | UI Designer & Backend Developer | [GitHub](https://github.com/colochoo) |
| Ricardo Campos | Algorithm Implementer | [GitHub](https://github.com/ricardorickycampos) |
| Braden Mizell | Documentation Writer | [GitHub](https://github.com/BradenMizell) |
| Evan Banks | Documentation Formatter | [GitHub](https://github.com/ebanks28) |
| Alice Johnson | Documentation Writer | [GitHub](https://github.com/BarBabe)|
| David Odumade | Algorithm Designer | [missing info] |

---

**Course:** CS 4306 – Algorithm Analysis  
**Institution:** Kennesaw State University  

## *License*

This project is licensed under the MIT License — see the [LICENSE](documentation/LICENSE) file for details.
