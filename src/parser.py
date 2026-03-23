import csv
import ast


#cleans up the inputs and turns them into nicer lists
def parse_list_field(field):
    if not field or field == "[]":
        return []
    try:
        return [x.strip() for x in field.strip("[]").split(",")]
    except:
        return []

#Loads all the variables from the dataset.
#right now im just using the example inputs at the bottom of the UCTS pdf as our dataset
def load_rooms(filepath):
    rooms = {}
    with open(filepath, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rooms[row["room_id"]] = {
                "capacity": int(row["capacity"]),
                "is_lab": row["is_lab"].lower() == "true",
                "building": row["building"]
            }
    return rooms

def load_timeslots(filepath):
    timeslots = []
    timeslot_info = {}

    with open(filepath, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts_id = row["slot_id"]
            timeslots.append(ts_id)

            timeslot_info[ts_id] = {
                "day": row["day"],
                "start": row["start_time"],
                "duration": int(row["duration_min"])
            }

    return timeslots, timeslot_info

def load_instructors(filepath):
    instructors = {}

    with open(filepath, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            instructors[row["instructor_id"]] = {
                "domains": parse_list_field(row["domains"]),
                "unavailable": parse_list_field(row["unavailable_slots"]),
                "required_no_teach": parse_list_field(row["required_no_teach_slots"]),
                "preferred": parse_list_field(row["preferred_slots"])
            }

    return instructors

def load_sections(filepath):
    sections = []
    section_lookup = {}

    with open(filepath, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            section = {
                "id": row["section_id"],
                "course_id": row["course_id"],
                "enrollment": int(row["enrollment"]),
                "instructor": row["instructor_id"],
                "needs_lab": row["needs_lab"].lower() == "true",
                "cohort": row["cohort_id"],
                "building_pref": row["building_pref"]
            }

            sections.append(section)
            section_lookup[section["id"]] = section

    return sections, section_lookup