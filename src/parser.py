import xml.etree.ElementTree as ET

from classes import (
    Room,
    RoomSharing,
    CourseClass,
    RoomOption,
    TimeOption
)

def parse_bool(value: str) -> bool:
    return value.lower() == "true"


def parse_rooms(root):
    rooms = []

    rooms_section = root.find("rooms")

    for room_elem in rooms_section.findall("room"):
        sharing_obj = None

        sharing_elem = room_elem.find("sharing")
        if sharing_elem is not None:
            pattern_elem = sharing_elem.find("pattern")

            departments = {}
            for dep in sharing_elem.findall("department"):
                departments[dep.get("value")] = dep.get("id")

            sharing_obj = RoomSharing(
                pattern=pattern_elem.text.strip(),
                unit=int(pattern_elem.get("unit")),
                free_for_all=sharing_elem.find("freeForAll").get("value"),
                not_available=sharing_elem.find("notAvailable").get("value"),
                departments=departments,
            )

        location = room_elem.get("location", "0,0").split(",")

        room = Room(
            room_id=int(room_elem.get("id")),
            capacity=int(room_elem.get("capacity")),
            x=int(location[0]),
            y=int(location[1]),
            constraint=parse_bool(room_elem.get("constraint", "false")),
            discouraged=parse_bool(room_elem.get("discouraged", "false")),
            sharing=sharing_obj,
        )

        rooms.append(room)

    return rooms

def parse_classes(root):
    classes = []

    classes_section = root.find("classes")

    for class_elem in classes_section.findall("class"):
        instructors = []
        room_options = []
        time_options = []

        for inst_elem in class_elem.findall("instructor"):
            instructors.append(int(inst_elem.get("id")))

        for room_elem in class_elem.findall("room"):
            room_options.append(
                RoomOption(
                    room_id=int(room_elem.get("id")),
                    preference=int(float(room_elem.get("pref")))
                )
            )

        for time_elem in class_elem.findall("time"):
            time_options.append(
                TimeOption(
                    days=time_elem.get("days"),
                    start=int(time_elem.get("start")),
                    length=int(time_elem.get("length")),
                    break_time=int(time_elem.get("breakTime")),
                    preference=float(time_elem.get("pref")),
                )
            )

        room_ratio = class_elem.get("roomToLimitRatio")

        #helps for when dataset data is incomplete
        def get_int(elem, attr, default=0):
            value = elem.get(attr)
            return int(value) if value is not None else default

        course_class = CourseClass(
            class_id=get_int(class_elem, "id"),
            offering=get_int(class_elem, "offering"),
            config=get_int(class_elem, "config"),
            subpart=get_int(class_elem, "subpart"),
            department=get_int(class_elem, "department"),
            class_limit=get_int(class_elem, "classLimit"),
            committed=parse_bool(class_elem.get("committed", "false")),
            scheduler=get_int(class_elem, "scheduler"),
            dates=class_elem.get("dates", ""),
            room_to_limit_ratio=float(room_ratio) if room_ratio else None,
            instructors=instructors,
            room_options=room_options,
            time_options=time_options,
        )

        classes.append(course_class)

    return classes


def parse_timetable(xml_file):
    tree = ET.parse(xml_file)
    root = tree.getroot()

    rooms = parse_rooms(root)
    classes = parse_classes(root)

    return rooms, classes

