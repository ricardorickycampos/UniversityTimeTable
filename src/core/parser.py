from __future__ import annotations
from pathlib import Path
from typing import Optional, Union
try: 
  import xml.etree.ElementTree as ET
except ImportError: 
  from xml.etree import ElementTree as ET
from src.core.models import (Class, Enrollment, GroupConstraint, Room, RoomCandidate, RoomSharing,
                       Student, TimePattern, Timetable, parse_pref,
                       )

""" Parser file
Reads the XML file and parses out info to create the 'model' @core.models.py"""

def _parse_days(days_str: str) -> int: 
  """1010100 means Monday + Wednesday + Friday """
  mask = 0 
  for i, ch in enumerate(days_str): 
    if ch == '1': 
      mask |= (1 << i)
  return mask

def _parse_location(loc_str: Optional[str]) -> Optional[tuple[int,int]]:
  if not loc_str: 
    return None
  try: 
    x,y = loc_str.split(',')
    return(int(x), int(y))
  except (ValueError, IndexError):
    """ x,y location, currently not used"""
    return None

"""Per-entity parsers"""

def _parse_room(elem) -> Room: 
  """Returns Room Objects"""
  sharing = None
  share_elem = elem.find('sharing')
  if share_elem is not None: 
    pattern_elem = share_elem.find('pattern')
    unit_slots = int(pattern_elem.attrib.get('unit', '6'))
    depts = {
      d.attrib['value']: int(d.attrib['id'])
      for d in share_elem.findall('department')
    }
    sharing = RoomSharing(
      pattern=pattern_elem.text or '',
      unit_minutes=unit_slots * 5,
      departments=depts,
    )
  return Room(
    id=int(elem.attrib['id']),
    capacity=int(elem.attrib['capacity']),
    constraint=(elem.attrib.get('constraint') == 'true'),
    location=_parse_location(elem.attrib.get('location')),
    sharing=sharing,
  )

def _parse_class(elem) -> Class: 
  """Returns Class Objects"""
  rooms = [
    RoomCandidate(room_id=int(r.attrib['id']),pref=parse_pref(r.attrib['pref']))
    for r in elem.findall('room')
  ]
  times = [
    TimePattern(
      days=_parse_days(t.attrib['days']),
      start=int(t.attrib['start']),
      length=int(t.attrib['length']),
      break_time=int(t.attrib.get('breakTime', '0')),
      pref=parse_pref(t.attrib['pref']),
    )
    for t in elem.findall('time')
  ]
  instructor_ids = [int(i.attrib['id']) for i in elem.findall('instructor')]

  scheduler_raw = elem.attrib.get('scheduler')
  scheduler = int(scheduler_raw) if scheduler_raw else None

  parent_raw = elem.attrib.get('parent')
  parent_id = int(parent_raw) if parent_raw else None

  offering = int(elem.attrib.get('offering','-1'))
  config = int(elem.attrib.get('config', '-1'))

  return Class(
    id=int(elem.attrib['id']),
    offering=offering,
    config=config,
    subpart=int(elem.attrib['subpart']),
    class_limit=int(elem.attrib['classLimit']),
    department=int(elem.attrib['department']),
    scheduler=scheduler,
    committed=(elem.attrib.get('committed') == 'true'),
    dates=elem.attrib.get('dates', ''),
    parent_id=parent_id,
    instructor_ids=instructor_ids,
    candidate_rooms=rooms,
    candidate_times=times,
  )

def _resolve_parent_inheritance(classes: list) -> None:
  """Some classes inherit their offering/config from their parent. Denoted as -1 in XML.
  This function resolves that inheritance by copying the parent's values.
  Chains in data go up to 2 levels deep. Max 10 passes as a safety check.
  """
  by_id = {c.id: c for c in classes}
  changed = True
  passes = 0 
  while changed and passes < 10: 
    changed = False
    passes += 1 
    for c in classes: 
      if c.offering == -1 and c.parent_id is not None: 
        parent = by_id.get(c.parent_id)
        if parent is not None and parent.offering != -1: 
          c.offering = parent.offering
          c.config = parent.config
          changed = True
  unresolved = [c.id for c in classes if c.offering == -1]
  if unresolved: 
    raise ValueError(f'Unresolved offering/config: {unresolved[:10]}')
  
def _parse_student(elem) -> Student: 
  """ Returns Student objects."""
  enrollments = [
    Enrollment(
      offering_id=int(o.attrib['id']),
      weight=float(o.attrib.get('weight', '1.0')),
    )
    for o in elem.findall('offering')
  ]
  return Student(id=int(elem.attrib['id']), enrollments=enrollments)

def _parse_group_constraint(elem) -> GroupConstraint:
  """Returns GroupConstraint Objects"""
  return GroupConstraint(
    id=int(elem.attrib['id']),
    type=elem.attrib['type'],
    pref=parse_pref(elem.attrib['pref']),
    class_ids=[int(c.attrib['id']) for c in elem.findall('class')]
  )

"""Public API """
def parse_data(
    path: Union[str, Path],
    subset: Optional[int] = None,
) -> Timetable:
  """Parses the XML file and returns a Timetable object"""
  tree = ET.parse(str(path))
  root = tree.getroot()

  room_elem = root.find('rooms')
  rooms = [_parse_room(r) for r in room_elem.findall('room')] if room_elem is not None else []

  classes_elem = root.find('classes')
  classes = [_parse_class(c) for c in classes_elem.findall('class')] if classes_elem is not None else []
  _resolve_parent_inheritance(classes)

  gc_elem = root.find('groupConstraints')
  group_constraints = (
      [_parse_group_constraint(gc) for gc in gc_elem.findall('constraint')]
      if gc_elem is not None else []
  )

  students_elem = root.find('students')
  students = (
      [_parse_student(s) for s in students_elem.findall('student')]
      if students_elem is not None else []
  )

  if subset is not None and subset < len(classes):
      classes = classes[:subset]
      kept_class_ids = {c.id for c in classes}
      kept_offering_ids = {c.offering for c in classes}

      group_constraints = [
          gc for gc in group_constraints
          if all(cid in kept_class_ids for cid in gc.class_ids)
      ]

      filtered_students = []
      for s in students:
        kept = [e for e in s.enrollments if e.offering_id in kept_offering_ids]
        if kept:
          filtered_students.append(Student(id=s.id, enrollments=kept))
      students = filtered_students
  return Timetable(
        nr_days=int(root.attrib.get('nrDays', '7')),
        slots_per_day=int(root.attrib.get('slotsPerDay', '288')),
        term=root.attrib.get('term', ''),
        year=int(root.attrib.get('year', '0')),
        rooms=rooms,
        classes=classes,
        students=students,
        group_constraints=group_constraints,
    )