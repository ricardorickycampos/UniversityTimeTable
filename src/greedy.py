def greedy_schedule(sections, timeslots, rooms, instructors, section_lookup):
    schedule = {}

    def is_feasible(section, timeslot, room):
        inst = section["instructor"]

        if timeslot in instructors[inst]["unavailable"]:
            return False
        if timeslot in instructors[inst]["required_no_teach"]:
            return False

        if section["enrollment"] > rooms[room]["capacity"]:
            return False

        if section["needs_lab"] and not rooms[room]["is_lab"]:
            return False

        for s_id, (t, r) in schedule.items():
            other = section_lookup[s_id]

            if t == timeslot:
                if r == room:
                    return False
                if other["instructor"] == inst:
                    return False
                if other["cohort"] == section["cohort"]:
                    return False

        return True

    def soft_penalty(section, timeslot, room):
        penalty = 0
        inst = section["instructor"]

        if timeslot not in instructors[inst]["preferred"]:
            penalty += 1

        if rooms[room]["building"] != section["building_pref"]:
            penalty += 1

        for s_id, (t, r) in schedule.items():
            other = section_lookup[s_id]

            if other["cohort"] == section["cohort"]:
                if t != timeslot:
                    penalty += 1

        return penalty

    #Sorts sections and prioritizes labs
    sections_sorted = sorted(
        sections,
        key=lambda s: (-s["enrollment"], -int(s["needs_lab"]))
    )

    for section in sections_sorted:
        best_choice = None
        best_score = float("inf")

        for t in timeslots:
            for r in rooms:
                if not is_feasible(section, t, r):
                    continue

                score = soft_penalty(section, t, r)

                if score < best_score:
                    best_score = score
                    best_choice = (t, r)

        if best_choice is None:
            print(f"Failed to schedule {section['id']}")
            continue

        schedule[section["id"]] = best_choice

    return schedule