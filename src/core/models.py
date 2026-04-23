from __future__ import annotations
from dataclasses import dataclass,field
from typing import Optional

""" Model file
This is the data structure that is fed into the genetic algorithm.
Classes for each of the data types are defined below, parsed from the XML.
"""
PREF_REQUIRED_VALUE = -1000.0
PREF_PROHIBITED_VALUE = 1000.0

def parse_pref(raw: str) -> float:
  if raw == 'R': 
    return PREF_REQUIRED_VALUE
  if raw == 'P': 
    return PREF_PROHIBITED_VALUE
  return float(raw)

def is_required(pref: float) -> bool:
  return pref <= PREF_REQUIRED_VALUE + 1e-6

def is_prohibited(pref: float) -> bool:
  return pref >= PREF_PROHIBITED_VALUE - 1e-6

"""Rooms"""
@dataclass(frozen=True)
class RoomSharing:
  pattern: str
  unit_minutes: int
  departments: dict[str, int] = field(default_factory=dict)

@dataclass(frozen=True)
class Room:
  id: int
  capacity: int 
  constraint: bool
  location: Optional[tuple[int,int]] = None
  sharing: Optional[RoomSharing] = None

"""Time Patten / Meeting Time for a class"""
@dataclass(frozen=True)
class TimePattern:
 days: int
 start: int
 length: int
 break_time: int
 pref: float

"""Class / Offering"""
@dataclass(frozen=True)
class RoomCandidate: 
  room_id: int
  pref: float

@dataclass
class Class: 
  id: int
  offering: int
  config: int
  subpart: int
  class_limit: int
  department: int
  scheduler: Optional[int]
  committed: bool
  dates: str
  parent_id: Optional[int] = None
  instructor_ids: list[int] = field(default_factory=list)
  candidate_rooms: list[RoomCandidate] = field(default_factory=list)
  candidate_times: list[TimePattern] = field(default_factory=list)


"""Students"""
@dataclass(frozen=True)
class Enrollment: 
  offering_id: int 
  weight: float

@dataclass
class Student: 
  id: int
  enrollments: list[Enrollment] = field(default_factory=list)

"""Group constraints"""
@dataclass
class GroupConstraint: 
  id: int 
  type: str
  pref: float
  class_ids: list[int] = field(default_factory=list)

"""Top level Container
Holds all other data types as a TimeTable Object
"""
@dataclass
class Timetable:
  nr_days: int 
  slots_per_day: int 
  term: str
  year: int 
  rooms: list[Room]
  classes: list[Class]
  students: list[Student]
  group_constraints: list[GroupConstraint]

  rooms_by_id: dict[int, Room] = field(init=False, repr=False)
  classes_by_id: dict[int, Class] = field(init=False, repr=False)
  students_by_id: dict[int, Student] = field(init=False, repr=False)
  gc_by_id: dict[int, GroupConstraint] = field(init=False, repr=False)
  
  def __post_init__(self):
    self.rooms_by_id = {r.id: r for r in self.rooms}
    self.classes_by_id = {c.id: c for c in self.classes}
    self.students_by_id = {s.id: s for s in self.students}
    self.gc_by_id = {gc.id: gc for gc in self.group_constraints}

  def summary(self) -> str: 
    with_instr = sum(1 for c in self.classes if c.instructor_ids)
    avg_r = sum(len(c.candidate_rooms) for c in self.classes) / max(1, len(self.classes))
    avg_t = sum(len(c.candidate_times) for c in self.classes) / max(1, len(self.classes))
    total_enr = sum(len(s.enrollments) for s in self.students)
    return (
            f"Timetable: {self.term} {self.year}, "
            f"{self.nr_days} days x {self.slots_per_day} slots/day\n"
            f"  Rooms:             {len(self.rooms)}\n"
            f"  Classes:           {len(self.classes)} ({with_instr} with instructors)\n"
            f"  Avg candidate rooms per class: {avg_r:.1f}\n"
            f"  Avg candidate times per class: {avg_t:.1f}\n"
            f"  Students:          {len(self.students)}\n"
            f"  Enrollments:       {total_enr}\n"
            f"  Group constraints: {len(self.group_constraints)}"
        )