from parser import parse_timetable
from greedy import greedy_schedule, format_days, format_time


def main():
    rooms, classes, instructors, offerings = parse_timetable("../data/pu-fal07-llr.xml")

    room_lookup = {
        room.room_id: room
        for room in rooms
    }
    
    class_lookup = {
        course.class_id: course
        for course in classes
    }

    instructor_lookup = {
        instructor.instructor_id: instructor.name
        for instructor in instructors
    }

    offering_lookup = {
        offering.offering_id: offering.name
        for offering in offerings
    }

    assignments, unscheduled = greedy_schedule(classes, room_lookup)

    print(f"\nScheduled {len(assignments)} out of {len(classes)} classes\n")

    print("Scheduled Classes:")
    for class_id in sorted(assignments):
        assignment = assignments[class_id]
        course = class_lookup[class_id]
        time = assignment["time"]

        course_name = offering_lookup.get(
            course.offering, f"Offering {course.offering}"
        )

        instructor_names = [
            instructor_lookup.get(inst_id, f"Instructor {inst_id}")
            for inst_id in course.instructors
        ]

        days = format_days(time.days)
        start = format_time(time.start)
        end = format_time(time.start + time.length)

        print(
            f"Class {class_id:>4} | "
            f"{course_name:<20} | "
            f"Room {assignment['room']:>3} | "
            f"Instructor: {', '.join(instructor_names):<20} | "
            f"{days:<15} | "
            f"{start} - {end}"
        )

    print("\nUnscheduled Classes:")
    for class_id in sorted(unscheduled):
        course = class_lookup[class_id]
        course_name = offering_lookup.get(
            course.offering,
            f"Offering {course.offering}"
        )

        print(f"Class {class_id:>4} | {course_name}")


if __name__ == "__main__":
    main()