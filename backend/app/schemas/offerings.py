import uuid
from datetime import datetime, time

from pydantic import BaseModel

from app.models.enums import MeetingFrequency, MeetingType, TeacherRole


class TermRead(BaseModel):
    id: uuid.UUID
    code: str
    year: int
    term_number: int
    created_at: datetime


class SectionSubjectRead(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class SectionTeacherRead(BaseModel):
    id: uuid.UUID
    name: str
    role: TeacherRole
    position: int


class SectionMeetingRead(BaseModel):
    id: uuid.UUID
    weekday: int
    start_time: time
    end_time: time
    campus: str | None
    classroom: str | None
    frequency: MeetingFrequency
    meeting_type: MeetingType


class SectionRead(BaseModel):
    id: uuid.UUID
    code: str
    class_group: str | None
    display_name: str | None
    campus: str | None
    shift: str | None
    total_seats: int | None
    reserved_seats: int | None
    workload_code: str | None
    is_active: bool
    subject: SectionSubjectRead
    teachers: list[SectionTeacherRead]
    meetings: list[SectionMeetingRead]


class SectionListRead(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[SectionRead]
