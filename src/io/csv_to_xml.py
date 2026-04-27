"""CSV → UniTime 2.4 XML converter.

Reads the four required CSVs from the assignment spec:
  rooms.csv       : room_id, capacity, is_lab, building
  timeslots.csv   : slot_id, day, start_time, duration_min
  sections.csv    : section_id, course_id, enrollment, instructor_id,
                    needs_lab, cohort_id, building_pref
  instructors.csv : instructor_id, domains, unavailable_slots,
                    required_no_teach_slots, preferred_slots
  distances.csv   : from_bld, to_bld, walk_min  (optional)

Produces a UniTime 2.4 XML file compatible with the existing GA solver.

Usage:
    from src.io.csv_to_xml import convert_csv_to_xml
    convert_csv_to_xml(rooms, timeslots, sections, instructors, distances, output)

    or from CLI:
    python -m src.io.csv_to_xml \\
        --rooms data/csv/rooms.csv \\
        --timeslots data/csv/timeslots.csv \\
        --sections data/csv/sections.csv \\
        --instructors data/csv/instructors.csv \\
        --output data/uploaded_data.xml
"""
from __future__ import annotations

import ast
import csv
from pathlib import Path
from typing import Optional
import xml.etree.ElementTree as ET
from xml.dom import minidom

# Day name → bit index (bit 0 = Monday … bit 6 = Sunday)
_DAY_BIT = {'Mon': 0, 'Tue': 1, 'Wed': 2, 'Thu': 3, 'Fri': 4, 'Sat': 5, 'Sun': 6}

# Bit index → 7-char days bitmask string
_BIT_TO_DAYS = {i: ''.join('1' if j == i else '0' for j in range(7)) for i in range(7)}


def _time_to_slot(time_str: str) -> int:
    """Convert 'HH:MM' to 5-minute slot index from midnight."""
    h, m = map(int, time_str.strip().split(':'))
    return (h * 60 + m) // 5


def _parse_slot_list(raw: str) -> list[str]:
    """Parse '[ts1, ts2]' or '[]' or 'ts1' string to a list of slot IDs."""
    raw = raw.strip()
    if not raw or raw in ('[]', '""', "''"):
        return []
    try:
        parsed = ast.literal_eval(raw)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed]
        return [str(parsed).strip()]
    except Exception:
        raw = raw.strip('[]"\' ')
        return [x.strip().strip('"\'') for x in raw.split(',') if x.strip()]


def _dept_id_from_course(course_id: str) -> int:
    """Derive a stable integer department ID from the course prefix (e.g. CSCI → hash)."""
    prefix = ''.join(c for c in course_id if c.isalpha())[:6]
    return (hash(prefix) & 0xFFFF) % 20 + 1


def convert_csv_to_xml(
    rooms_path: Path,
    timeslots_path: Path,
    sections_path: Path,
    instructors_path: Path,
    output_path: Path,
    distances_path: Optional[Path] = None,
) -> None:
    """Convert CSVs to UniTime XML and write to output_path."""

    # ── Load CSVs ─────────────────────────────────────────────────────────────
    with open(rooms_path, newline='') as f:
        rooms = list(csv.DictReader(f))
    with open(timeslots_path, newline='') as f:
        timeslots = list(csv.DictReader(f))
    with open(sections_path, newline='') as f:
        sections = list(csv.DictReader(f))
    with open(instructors_path, newline='') as f:
        instructors_rows = list(csv.DictReader(f))

    distances: dict[tuple[str, str], int] = {}
    if distances_path and Path(distances_path).exists():
        with open(distances_path, newline='') as f:
            for row in csv.DictReader(f):
                distances[(row['from_bld'].strip(), row['to_bld'].strip())] = int(row['walk_min'])

    # ── Build lookup dicts ────────────────────────────────────────────────────
    instructors: dict[str, dict] = {r['instructor_id'].strip(): r for r in instructors_rows}
    room_int_id: dict[str, int] = {r['room_id'].strip(): i + 1 for i, r in enumerate(rooms)}
    instr_int_id: dict[str, int] = {iid: i + 1 for i, iid in enumerate(instructors)}

    # Offerings: one per unique course_id
    course_offering: dict[str, int] = {}
    _offer_ctr = [1]

    def get_offering(cid: str) -> int:
        if cid not in course_offering:
            course_offering[cid] = _offer_ctr[0]
            _offer_ctr[0] += 1
        return course_offering[cid]

    # ── Build XML root ────────────────────────────────────────────────────────
    root = ET.Element('timetable')
    root.set('version', '2.4')
    root.set('initiative', 'csvImport')
    root.set('term', '2026Spr')
    root.set('year', '2026')
    root.set('nrDays', '7')
    root.set('slotsPerDay', '288')

    # ── Rooms ─────────────────────────────────────────────────────────────────
    rooms_elem = ET.SubElement(root, 'rooms')
    for r in rooms:
        rid = r['room_id'].strip()
        re = ET.SubElement(rooms_elem, 'room')
        re.set('id', str(room_int_id[rid]))
        re.set('constraint', 'true')
        re.set('capacity', r['capacity'].strip())
        re.set('location', '0,0')

    # ── Classes ───────────────────────────────────────────────────────────────
    classes_elem = ET.SubElement(root, 'classes')
    cohort_class_ids: dict[str, list[int]] = {}

    for sec_idx, sec in enumerate(sections):
        class_id = sec_idx + 1
        course_id = sec['course_id'].strip()
        offering_id = get_offering(course_id)
        inst_key = sec.get('instructor_id', '').strip()
        inst = instructors.get(inst_key, {})
        needs_lab = sec.get('needs_lab', 'false').strip().lower() == 'true'
        enrollment = int(sec.get('enrollment', '30').strip())
        building_pref = sec.get('building_pref', '').strip()
        cohort = sec.get('cohort_id', '').strip()

        # Instructor slot constraints
        unavail = set(_parse_slot_list(inst.get('unavailable_slots', '[]')))
        req_no_teach = set(_parse_slot_list(inst.get('required_no_teach_slots', '[]')))
        preferred = set(_parse_slot_list(inst.get('preferred_slots', '[]')))
        hard_blocked = unavail | req_no_teach

        ce = ET.SubElement(classes_elem, 'class')
        ce.set('id', str(class_id))
        ce.set('offering', str(offering_id))
        ce.set('config', str(offering_id))
        ce.set('subpart', '1')
        ce.set('classLimit', str(enrollment))
        ce.set('department', str(_dept_id_from_course(course_id)))
        ce.set('committed', 'false')
        ce.set('dates', '1' * 52)

        if inst_key and inst_key in instr_int_id:
            ie = ET.SubElement(ce, 'instructor')
            ie.set('id', str(instr_int_id[inst_key]))

        # Candidate rooms: filter by capacity and lab requirement
        for r in rooms:
            rid = r['room_id'].strip()
            r_cap = int(r['capacity'].strip())
            r_is_lab = r.get('is_lab', 'false').strip().lower() == 'true'
            if r_cap < enrollment:
                continue
            if needs_lab and not r_is_lab:
                continue
            if not needs_lab and r_is_lab:
                continue
            pref = '-1' if (building_pref and r.get('building', '').strip() == building_pref) else '1'
            re_c = ET.SubElement(ce, 'room')
            re_c.set('id', str(room_int_id[rid]))
            re_c.set('pref', pref)

        # Candidate times: all slots not hard-blocked
        for ts in timeslots:
            slot_id = ts['slot_id'].strip()
            if slot_id in hard_blocked:
                continue
            day_idx = _DAY_BIT.get(ts['day'].strip(), 0)
            days_str = _BIT_TO_DAYS[day_idx]
            start = _time_to_slot(ts['start_time'])
            length = int(ts['duration_min'].strip()) // 5
            pref = 'R' if slot_id in preferred else '0'
            te = ET.SubElement(ce, 'time')
            te.set('days', days_str)
            te.set('start', str(start))
            te.set('length', str(length))
            te.set('breakTime', '0')
            te.set('pref', pref)

        if cohort:
            cohort_class_ids.setdefault(cohort, []).append(class_id)

    # ── Group Constraints: same-cohort sections cannot overlap ────────────────
    gc_elem = ET.SubElement(root, 'groupConstraints')
    gc_id = 1
    for cohort, cids in cohort_class_ids.items():
        if len(cids) < 2:
            continue
        gce = ET.SubElement(gc_elem, 'constraint')
        gce.set('id', str(gc_id))
        gce.set('type', 'SAME_STUDENTS')
        gce.set('pref', 'P')
        for cid in cids:
            cc = ET.SubElement(gce, 'class')
            cc.set('id', str(cid))
        gc_id += 1

    # ── Students: one proxy student per cohort ────────────────────────────────
    students_elem = ET.SubElement(root, 'students')
    for stu_idx, (cohort, cids) in enumerate(cohort_class_ids.items()):
        se = ET.SubElement(students_elem, 'student')
        se.set('id', str(stu_idx + 1))
        seen = set()
        for cid in cids:
            sec = sections[cid - 1]
            oid = get_offering(sec['course_id'].strip())
            if oid not in seen:
                oe = ET.SubElement(se, 'offering')
                oe.set('id', str(oid))
                oe.set('weight', '1.0')
                seen.add(oid)

    # ── Serialize ─────────────────────────────────────────────────────────────
    raw = ET.tostring(root, encoding='unicode')
    pretty = minidom.parseString(raw).toprettyxml(indent='  ')
    lines = pretty.splitlines()
    lines[0] = '<?xml version="1.0" encoding="UTF-8"?>'
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f'Converted {len(sections)} sections, {len(rooms)} rooms, '
          f'{len(timeslots)} timeslots → {output_path}')


# ── CLI entry point ───────────────────────────────────────────────────────────
if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description='Convert UCTP CSV files to UniTime XML')
    p.add_argument('--rooms',       required=True, type=Path)
    p.add_argument('--timeslots',   required=True, type=Path)
    p.add_argument('--sections',    required=True, type=Path)
    p.add_argument('--instructors', required=True, type=Path)
    p.add_argument('--distances',   default=None,  type=Path)
    p.add_argument('--output',      required=True, type=Path)
    args = p.parse_args()
    convert_csv_to_xml(
        rooms_path=args.rooms,
        timeslots_path=args.timeslots,
        sections_path=args.sections,
        instructors_path=args.instructors,
        distances_path=args.distances,
        output_path=args.output,
    )
