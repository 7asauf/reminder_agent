from datetime import datetime, timedelta

from db import changes_on

LEAD = timedelta(minutes=10)  # how early to warn before a class

TEACHERS = {
    "AAR": "Aashnan Rahman",
    "AFZ": "Anika Farzana",
    "KHA": "Khalid Hasan Ador",
    "MI": "Dr. Mohayeminul Islam",
    "RHJ": "Reaz Hassan Joarder",
    "SAR": "Sumaiya Ahmed Rani",
    "SN": "Samia Nawsheen",
    "SRR": "Syed Rifat Raiyan",
    "TAS": "Tanjila Alam Sathi",
    "TRT": "Dr. Tajkia Rahman Toma",
    "TZF": "Md. Tariquzzaman Faisal",
}

COURSES = {
    "Math 4341": "Linear Algebra",
    "CSE 4303": "Data Structures",
    "CSE 4304": "Data Structures Lab",
    "CSE 4305": "Computer Organization and Architecture",
    "CSE 4307": "Database Management Systems",
    "CSE 4308": "Database Management Systems Lab",
    "CSE 4309": "Theory of Computing",
    "SWE 4301": "Object Oriented Concepts II",
    "SWE 4302": "Object Oriented Concepts II Lab",
    "SWE 4304": "Software Project Lab I",  # not in the timetable image, so no slot below yet
}

# Lab group B.  (weekday: 0=Mon ... 4=Fri, start, end, course code, room, teacher codes)
# This is the regular WEEKLY routine. One-off changes (cancelled / moved on a single date)
# live in the database and are applied by schedule_for(). To change the routine for the
# whole semester, edit this list.
CLASSES = [
    (0, "09:15", "10:30", "CSE 4309", "R-304", "SRR"),
    (0, "10:30", "11:45", "CSE 4305", "R-302", "TAS"),
    (0, "11:45", "13:00", "SWE 4301", "R-205", "MI"),
    (0, "14:30", "15:45", "CSE 4303", "R-304", "RHJ"),
    (1, "09:15", "10:30", "CSE 4305", "R-510", "TAS"),
    (1, "10:30", "13:00", "CSE 4304", "L-1", "RHJ/SAR"),
    (1, "14:30", "15:45", "SWE 4301", "R-510", "MI"),
    (2, "08:00", "09:40", "CSE 4308", "L-5", "TZF/SN"),  # CHECK: real start time of this 100-min lab
    (2, "10:30", "11:45", "CSE 4307", "R-106 (AB3)", "TZF"),
    (3, "08:00", "09:15", "Math 4341", "R-304", "SN"),
    (3, "10:30", "13:00", "SWE 4302", "L-3", "MI/KHA"),
    (3, "14:30", "15:45", "CSE 4309", "R-304", "SRR"),
    (4, "08:00", "09:15", "Math 4341", "R-106 (AB3)", "SN"),
    (4, "10:30", "11:45", "CSE 4303", "R-304", "RHJ"),
    (4, "11:45", "13:00", "CSE 4307", "R-304", "TZF"),
]


def teacher_names(codes):
    return ", ".join(TEACHERS.get(code, code) for code in codes.split("/"))


def course_label(code):
    title = COURSES.get(code)
    return f"{title} ({code})" if title else code


def classes_on(day):
    """day is a datetime.date. The REGULAR weekly classes for that weekday, earliest first."""
    return sorted((c for c in CLASSES if c[0] == day.weekday()), key=lambda c: c[1])


def schedule_for(day):
    """The real schedule for a date: the weekly routine with that date's changes applied."""
    changes = {course: (kind, s, e, r) for _id, course, kind, s, e, r in changes_on(day.isoformat())}
    result = []
    for weekday, start, end, course, room, teachers in classes_on(day):
        kind, new_start, new_end, new_room = changes.get(course, (None, None, None, None))
        if kind == "cancel":
            continue
        if kind == "move":
            start = new_start or start
            end = new_end or end
            room = f"{new_room or room} (rescheduled)"
        result.append((weekday, start, end, course, room, teachers))
    return sorted(result, key=lambda c: c[1])


def cancelled_on(day):
    """Course codes of regular classes cancelled on that date."""
    return [course for _id, course, kind, *_ in changes_on(day.isoformat()) if kind == "cancel"]


def format_class(c):
    _, start, end, course, room, teachers = c
    return f"{start}-{end}  {course_label(course)}\n   ↳ {room} · {teacher_names(teachers)}"


def due_class_alerts(now):
    """now is a timezone-aware datetime. Returns [(dedupe_key, message)] for classes
    whose 10-minute warning window is open right now."""
    alerts = []
    for c in schedule_for(now.date()):
        _, start, end, course, room, teachers = c
        start_at = datetime.combine(
            now.date(), datetime.strptime(start, "%H:%M").time(), tzinfo=now.tzinfo
        )
        if start_at - LEAD <= now < start_at:
            key = f"class_alert:{now.date().isoformat()}:{start}:{course}"
            alerts.append((key, f"🎓 {course_label(course)} at {start}\n{room} · {teacher_names(teachers)}"))
    return alerts