<div align="center">
  <h1>UniversityTimeTable</h1>
</div>

## Introduction
This project is to come up with a solve the University Course TimeTabling Problem (UCTP) by designing a system capable of scheduling 10,000+ Students and 500+ Courses within Kennesaw State University.
This is a collaborative effort for the Course CS 4306 - Algorithm Analysis
## Usage
Requirements:
- Python 3.10+
### Install requirements
```bash
pip install -r requirements.txt
```
### Set up:
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
After running the output will be saved to results/ folder.

## Goal 

- Generate a conflict free schedule for a simulated university of 10,000+ Students.
- Maximize compactness by minimizing idle gaps between lectures for students cohorts.
- Show runtime & improvement curves, explain ordering/pruning; provide one-command reproducibilty i.e. fixed seed.

## Constraints 

### Hard
- **Non-Overlap:** (Conflict-Free): No double booking.
- **Room capacity:** Enrollment must not exceed a rooms seats. 
- **Resource & suitability:** Room much have required equipment for course.
- **Course structure relationships:** Valid combinations must be maintained e.i. lecture & labs. 
- **Instructor domain/qualification suitability:** Section must be assigned to a qualifed instructor.
- **Instructor availability & required preferences:** Explicitly blocked out times/days by instructors are non-negotiable.
- **Travel time limits:** For any individual, back to back classes must allow a feasible walk time.

### Soft 
- **Minimizing student gaps:** Reduce idle time to as low as possible.
- **Hybrid modeling:** Allow courses marked as hybrid/online to use a virtual room.
- **Instructor workload distribution:** Define reasonable limits to instructors work time.
- **Preference satisfaction:** Track when a non-required faculty preference timeslop is honored.

## Resources

1. Abdipoor, S., Yaakob, R., Goh, S.L. and Abdullah, S., 2023. Meta-heuristic approaches for the university course
timetabling problem. Intelligent Systems with Applications, 19, p.200253.
