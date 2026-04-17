import csv

def export_rooms_csv(rooms):
    with open("rooms.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "room_id", "capacity", "x", "y",
            "constraint", "discouraged"
        ])

        for room in rooms:
            writer.writerow([
                room.room_id,
                room.capacity,
                room.x,
                room.y,
                room.constraint,
                room.discouraged,
            ])


    with open("room_sharing.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "room_id", "unit", "pattern",
            "free_for_all", "not_available", "departments"
        ])

        for room in rooms:
            if room.sharing is not None:
                writer.writerow([
                    room.room_id,
                    room.sharing.unit,
                    room.sharing.pattern,
                    room.sharing.free_for_all,
                    room.sharing.not_available,
                    str(room.sharing.departments),
                ])

def export_classes_csv(classes):
    with open("classes.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "class_id", "offering", "config", "subpart",
            "department", "class_limit", "committed",
            "scheduler", "dates", "room_to_limit_ratio"
        ])

        for c in classes:
            writer.writerow([
                c.class_id,
                c.offering,
                c.config,
                c.subpart,
                c.department,
                c.class_limit,
                c.committed,
                c.scheduler,
                c.dates,
                c.room_to_limit_ratio,
            ])

    with open("class_instructors.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["class_id", "instructor_id"])

        for c in classes:
            for inst in c.instructors:
                writer.writerow([c.class_id, inst])

    with open("class_room_options.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["class_id", "room_id", "preference"])

        for c in classes:
            for room in c.room_options:
                writer.writerow([
                    c.class_id,
                    room.room_id,
                    room.preference,
                ])

    with open("class_time_options.csv", "w", newline="") as f:
        writer.writerow([
            "class_id", "days", "start", "length",
            "break_time", "preference"
        ])

        for c in classes:
            for time in c.time_options:
                writer.writerow([
                    c.class_id,
                    time.days,
                    time.start,
                    time.length,
                    time.break_time,
                    time.preference,
                ])