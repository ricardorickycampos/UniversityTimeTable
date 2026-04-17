"""
ITC 2007 University Timetabling XML -> Pandas DataFrames
Parses all 4 sections: rooms, classes (with times/rooms/instructors), constraints, students
"""

import xml.etree.ElementTree as ET
import pandas as pd


def parse_timetable(xml_path: str) -> dict[str, pd.DataFrame]:
    tree = ET.parse(xml_path)
    root = tree.getroot()

    return {
        "rooms":       _parse_rooms(root),
        "classes":     _parse_classes(root),
        "times":       _parse_times(root),       # one row per available time slot per class
        "instructors": _parse_instructors(root),  # one row per instructor assignment per class
        "constraints": _parse_constraints(root),
        "students":    _parse_students(root),
    }


# ── 1. Rooms ──────────────────────────────────────────────────────────────────

def _parse_rooms(root) -> pd.DataFrame:
    rows = []
    for room in root.find("rooms") or []:
        loc = room.get("location")
        x, y = (loc.split(",") if loc else (None, None))
        rows.append({
            "room_id":      room.get("id"),
            "capacity":     int(room.get("capacity", 0)),
            "loc_x":        float(x) if x else None,
            "loc_y":        float(y) if y else None,
            "constraint":   room.get("constraint", "true") == "true",
            "discouraged":  room.get("discouraged", "false") == "true",
            "ignore_too_far": room.get("ignoreTooFar", "false") == "true",
            "has_sharing":  room.find("sharing") is not None,
        })
    return pd.DataFrame(rows)


# ── 2. Classes (core attributes) ─────────────────────────────────────────────

def _parse_classes(root) -> pd.DataFrame:
    rows = []
    for cls in root.find("classes") or []:
        rows.append({
            "class_id":       cls.get("id"),
            "offering_id":    cls.get("offering"),
            "config_id":      cls.get("config"),
            "subpart_id":     cls.get("subpart"),
            "parent_id":      cls.get("parent"),
            "scheduler":      cls.get("scheduler"),
            "committed":      cls.get("committed", "false") == "true",
            "class_limit":    cls.get("classLimit"),
            "min_class_limit":cls.get("minClassLimit"),
            "max_class_limit":cls.get("maxClassLimit"),
            "nr_rooms":       int(cls.get("nrRooms", 1)),
            "dates":          cls.get("dates"),
            # Solution placements (room and time marked solution="true")
            "solution_room":  next(
                (r.get("id") for r in cls.findall("room") if r.get("solution") == "true"), None
            ),
            "solution_time_days": next(
                (t.get("days") for t in cls.findall("time") if t.get("solution") == "true"), None
            ),
            "solution_time_start": next(
                (t.get("start") for t in cls.findall("time") if t.get("solution") == "true"), None
            ),
            "solution_time_length": next(
                (t.get("length") for t in cls.findall("time") if t.get("solution") == "true"), None
            ),
        })
    return pd.DataFrame(rows)


# ── 3. Available time slots (one row per class × time option) ─────────────────

def _parse_times(root) -> pd.DataFrame:
    rows = []
    for cls in root.find("classes") or []:
        for t in cls.findall("time"):
            rows.append({
                "class_id":  cls.get("id"),
                "days":      t.get("days"),
                "start":     int(t.get("start")),
                "length":    int(t.get("length")),
                "pref":      float(t.get("pref", 0)),
                "is_solution": t.get("solution") == "true",
            })
    return pd.DataFrame(rows)


# ── 4. Instructor assignments ─────────────────────────────────────────────────

def _parse_instructors(root) -> pd.DataFrame:
    rows = []
    for cls in root.find("classes") or []:
        for instr in cls.findall("instructor"):
            rows.append({
                "class_id":      cls.get("id"),
                "instructor_id": instr.get("id"),
                "is_solution":   instr.get("solution") == "true",
            })
    return pd.DataFrame(rows)


# ── 5. Group / distribution constraints ──────────────────────────────────────

def _parse_constraints(root) -> pd.DataFrame:
    rows = []
    for con in root.find("groupConstraints") or []:
        class_ids = [c.get("id") for c in con.findall("class")]
        parent_ids = [c.get("id") for c in con.findall("parentClass")]
        rows.append({
            "constraint_id":  con.get("id"),
            "type":           con.get("type"),
            "pref":           con.get("pref"),
            "course_limit":   con.get("courseLimit"),
            "delta":          con.get("delta"),
            "class_ids":      class_ids,        # list
            "parent_class_ids": parent_ids,     # list
            "n_classes":      len(class_ids),
        })
    return pd.DataFrame(rows)


# ── 6. Students ───────────────────────────────────────────────────────────────

def _parse_students(root) -> pd.DataFrame:
    rows = []
    for student in root.find("students") or []:
        sid = student.get("id")
        offerings = [
            {"student_id": sid, "offering_id": o.get("id"), "weight": float(o.get("weight", 1.0))}
            for o in student.findall("offering")
        ]
        enrolled = [c.get("id") for c in student.findall("class")]
        prohibited = [c.get("id") for c in student.findall("prohibited-class")]
        rows.append({
            "student_id":       sid,
            "offerings":        [o["offering_id"] for o in offerings],
            "weights":          [o["weight"] for o in offerings],
            "enrolled_classes": enrolled,
            "prohibited_classes": prohibited,
        })
    return pd.DataFrame(rows)


# ── Helper: decode days binary string → human-readable ───────────────────────

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

def decode_days(days_str: str) -> str:
    """'1010100' -> 'Mon/Wed/Fri'"""
    return "/".join(d for d, bit in zip(DAY_NAMES, days_str) if bit == "1")

def slot_to_time(slot: int) -> str:
    """Convert a slot number (5-min slots from midnight) to HH:MM."""
    minutes = slot * 5
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "timetable.xml"
    dfs = parse_timetable(path)

    for name, df in dfs.items():
        print(f"\n{'='*60}")
        print(f"  {name.upper()}  ({len(df)} rows × {len(df.columns)} cols)")
        print('='*60)
        print(df.head(5).to_string(index=False))

    # Example: show human-readable solution times for classes
    times_df = dfs["times"]
    if not times_df.empty:
        sol = times_df[times_df["is_solution"]].copy()
        sol["day_names"] = sol["days"].apply(decode_days)
        sol["start_time"] = sol["start"].apply(slot_to_time)
        sol["end_time"] = (sol["start"] + sol["length"]).apply(slot_to_time)
        print("\n\nSOLUTION TIMES (human-readable):")
        print(sol[["class_id", "day_names", "start_time", "end_time", "pref"]].head(10).to_string(index=False))
