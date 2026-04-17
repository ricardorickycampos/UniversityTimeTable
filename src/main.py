from parser import parse_timetable
from greedy import greedy_schedule, format_days, format_time


def main():
    rooms, classes = parse_timetable("../data/pu-fal07-llr.xml")

    room_lookup = {room.room_id: room for room in rooms}

    assignments, unscheduled = greedy_schedule(classes, room_lookup)

    print(f"\nScheduled {len(assignments)} out of {len(classes)} classes\n")

    print("Scheduled Classes:")
    for class_id in sorted(assignments):
        assignment = assignments[class_id]
        time = assignment["time"]

        days = format_days(time.days)
        start = format_time(time.start)
        end = format_time(time.start + time.length)

        print(
            f"Class {class_id:>4} | "
            f"Room {assignment['room']:>3} | "
            f"{days:<15} | "
            f"{start} - {end}"
        )

    print("\nUnscheduled Classes:")
    for class_id in sorted(unscheduled):
        print(f"Class {class_id}")


if __name__ == "__main__":
    main()