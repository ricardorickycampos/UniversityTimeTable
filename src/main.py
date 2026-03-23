from parser import *
from greedy import greedy_schedule

def main():
    #Filepaths
    rooms_file = "../data/UCTS_Rooms_Test.csv"
    timeslots_file = "../data/UCTS_Timeslots_Test.csv"
    instructors_file = "../data/UCTS_Instructors_Test.csv"
    sections_file = "../data/UCTS_Sections_Test.csv"

    #loading the data from the dataset
    rooms = load_rooms(rooms_file)
    timeslots, timeslot_info = load_timeslots(timeslots_file)
    instructors = load_instructors(instructors_file)
    sections, section_lookup = load_sections(sections_file)

    #Running the search
    schedule = greedy_schedule(
        sections,
        timeslots,
        rooms,
        instructors,
        section_lookup
    )

    #Output schedule
    print("\nFinal Schedule:\n")
    for sec, (t, r) in schedule.items():
        s = section_lookup[sec]

        print(
            f"{sec} | Course: {s['course_id']} | "
            f"Instructor: {s['instructor']} | "
            f"Timeslot: {t} | Room: {r}"
        )

if __name__ == "__main__":
    main()