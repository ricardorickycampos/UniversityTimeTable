from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class RoomSharing:
    pattern: str
    unit: int
    free_for_all: str
    not_available: str
    departments: dict[str, str]


@dataclass
class Room:
    room_id: int
    capacity: int
    x: int
    y: int
    constraint: bool
    discouraged: bool = False
    sharing: Optional[RoomSharing] = None


@dataclass
class TimeOption:
    days: str
    start: int
    length: int
    break_time: int
    preference: float


@dataclass
class RoomOption:
    room_id: int
    preference: int


@dataclass
class CourseClass:
    class_id: int
    offering: int
    config: int
    subpart: int
    department: int
    class_limit: int
    committed: bool
    scheduler: int
    dates: str
    room_to_limit_ratio: Optional[float] = None
    instructors: List[int] = field(default_factory=list)
    room_options: List[RoomOption] = field(default_factory=list)
    time_options: List[TimeOption] = field(default_factory=list)

@dataclass
class Instructor:
    instructor_id: int
    external_id: str
    name: str

@dataclass
class Offering:
    offering_id: int
    name: str
    course: str
    subject_area: str