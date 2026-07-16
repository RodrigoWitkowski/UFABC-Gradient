import re
from dataclasses import dataclass
from datetime import time

from app.models.enums import MeetingFrequency, MeetingType
from app.services.normalization.text import clean_text, strip_accents

WEEKDAYS = {
    "segunda": 0,
    "terca": 1,
    "quarta": 2,
    "quinta": 3,
    "sexta": 4,
    "sabado": 5,
    "domingo": 6,
}

MEETING_RE = re.compile(
    r"(?P<weekday>segunda|terca|quarta|quinta|sexta|sabado|domingo)"
    r"(?:-feira)?\s+das?\s+"
    r"(?P<start>\d{1,2}:\d{2})\s+(?:as|a)\s+(?P<end>\d{1,2}:\d{2})",
    re.IGNORECASE,
)
ROOM_RE = re.compile(
    r"(?:^|[,;])\s*sala\s+(?P<room>.*?)(?=(?:[,;]\s*(?:semanal|quinzenal))|$)",
    re.IGNORECASE,
)
FREQUENCY_RE = re.compile(r"\b(semanal|quinzenal(?:\s+(?:i{1,2}|1|2))?)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ParsedMeeting:
    weekday: int
    start_time: time
    end_time: time
    campus: str | None
    classroom: str | None
    frequency: MeetingFrequency
    meeting_type: MeetingType

    def as_snapshot(self) -> dict[str, str | int | None]:
        return {
            "weekday": self.weekday,
            "start_time": self.start_time.isoformat(timespec="minutes"),
            "end_time": self.end_time.isoformat(timespec="minutes"),
            "campus": self.campus,
            "classroom": self.classroom,
            "frequency": self.frequency.value,
            "meeting_type": self.meeting_type.value,
        }


def _parse_frequency(chunk: str) -> MeetingFrequency:
    match = FREQUENCY_RE.search(strip_accents(chunk).casefold())
    if match is None:
        return MeetingFrequency.OTHER
    value = match.group(1).casefold()
    if value == "semanal":
        return MeetingFrequency.WEEKLY
    if value.endswith((" ii", " 2")):
        return MeetingFrequency.BIWEEKLY_II
    return MeetingFrequency.BIWEEKLY_I


def parse_schedule(
    value: object,
    *,
    campus: str | None,
    meeting_type: MeetingType,
) -> list[ParsedMeeting]:
    text = clean_text(value)
    if text is None or text == "0":
        return []

    searchable = strip_accents(text).casefold()
    matches = list(MEETING_RE.finditer(searchable))
    if not matches:
        raise ValueError(f"horario nao reconhecido: {text}")

    meetings: list[ParsedMeeting] = []
    for index, match in enumerate(matches):
        chunk_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        chunk = text[match.end() : chunk_end]
        room_match = ROOM_RE.search(chunk)
        classroom = clean_text(room_match.group("room")) if room_match else None
        start = time.fromisoformat(match.group("start"))
        end = time.fromisoformat(match.group("end"))
        if end <= start:
            raise ValueError(f"horario final deve ser posterior ao inicial: {text}")
        meetings.append(
            ParsedMeeting(
                weekday=WEEKDAYS[match.group("weekday").casefold()],
                start_time=start,
                end_time=end,
                campus=clean_text(campus),
                classroom=classroom,
                frequency=_parse_frequency(chunk),
                meeting_type=meeting_type,
            )
        )
    return meetings
