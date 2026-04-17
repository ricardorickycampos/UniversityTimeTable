from parse_timetable import parse_timetable, decode_days, slot_to_time

dfs = parse_timetable("data/data.xml")

rooms_df       = dfs["rooms"]
classes_df     = dfs["classes"]
times_df       = dfs["times"]
instructors_df = dfs["instructors"]
constraints_df = dfs["constraints"]
students_df    = dfs["students"]

# Decode a time slot to human-readable
slot_to_time(102)     # → "08:30"
decode_days("1010100") # → "Mon/Wed/Fri"