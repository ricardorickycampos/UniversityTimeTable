def class_difficulty(course):
    return len(course.room_options) * len(course.time_options)


def overlaps(time1, time2):
    #same day checking
    for i in range(len(time1.days)):
        if time1.days[i] == '1' and time2.days[i] == '1':
            start1 = time1.start
            end1 = time1.start + time1.length

            start2 = time2.start
            end2 = time2.start + time2.length

            if start1 < end2 and start2 < end1:
                return True
    return False

def format_days(day_string):
    #turns the binary for the days into actual days
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    result = []
    for i, ch in enumerate(day_string):
        if ch == "1":
            result.append(day_names[i])

    return "/".join(result)


def format_time(slot):
    #helps make the time part of the dataset less ugly
    total_minutes = slot * 5

    hours = total_minutes // 60
    minutes = total_minutes % 60

    suffix = "AM"
    if hours >= 12:
        suffix = "PM"

    display_hour = hours % 12
    if display_hour == 0:
        display_hour = 12

    return f"{display_hour}:{minutes:02d} {suffix}"

def greedy_schedule(classes, room_lookup):
    unscheduled = []

    room_schedule = {}         #room_id -> list of assigned time options
    instructor_schedule = {}   #instructor_id -> list of assigned time options

    assignments = {}

    sorted_classes = sorted(classes, key=class_difficulty)

    for course in sorted_classes:
        assigned = False

        #sort by best preference first
        time_options = sorted(course.time_options, key=lambda t: t.preference, reverse=True)
        room_options = sorted(course.room_options, key=lambda r: r.preference, reverse=True)

        for time in time_options:
            for room in room_options:

                #capacity check
                room_obj = room_lookup[room.room_id]

                if room_obj.capacity < course.class_limit:
                    continue

                #room conflict check
                room_conflict = False
                if room.room_id in room_schedule:
                    for existing_time in room_schedule[room.room_id]:
                        if overlaps(time, existing_time):
                            room_conflict = True
                            break

                if room_conflict:
                    continue

                #instructor conflict check
                instructor_conflict = False
                for instructor in course.instructors:
                    if instructor in instructor_schedule:
                        for existing_time in instructor_schedule[instructor]:
                            if overlaps(time, existing_time):
                                instructor_conflict = True
                                break

                if instructor_conflict:
                    continue

                #assignment found
                assignments[course.class_id] = {
                    "room": room.room_id,
                    "time": time
                }

                room_schedule.setdefault(room.room_id, []).append(time)

                for instructor in course.instructors:
                    instructor_schedule.setdefault(instructor, []).append(time)

                assigned = True
                break

            if assigned:
                break

        if not assigned:
            unscheduled.append(course.class_id)

    return assignments, unscheduled